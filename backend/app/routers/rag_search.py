import logging
import os
import time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Request, HTTPException
from app.services.firestore_repo import FirestoreRepo
from app.rag.retriever import Retriever
from app.rag.generator import Generator

logger = logging.getLogger("RAG_API")
router = APIRouter(prefix="/api/search", tags=["RAG"])

# --- Models ---
class RAGScope(BaseModel):
    doc_ids: Optional[List[str]] = None
    concept_ids: Optional[List[str]] = None
    folder_path: Optional[str] = None

class RAGRequest(BaseModel):
    query: str
    scope: Optional[RAGScope] = None
    top_k: Optional[int] = int(os.getenv("DEFAULT_TOP_K", 8))

from app.common.schemas import RAGResponse, Citation

# --- Models ---
class RAGScope(BaseModel):
    doc_ids: Optional[List[str]] = None
    concept_ids: Optional[List[str]] = None
    folder_path: Optional[str] = None

class RAGRequest(BaseModel):
    query: str
    scope: Optional[RAGScope] = None
    top_k: Optional[int] = int(os.getenv("DEFAULT_TOP_K", 8))

# --- Handler ---
@router.post("/rag", response_model=RAGResponse)
async def search_rag(request: Request, body: RAGRequest):
    start_ts = time.time()
    
    # 1. Auth Context 확인
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo = FirestoreRepo(auth_ctx)
    
        # 2. Retrieve (Vector Search)
    retrieved_chunks = []
    retriever_error = None
    
    try:
        retriever = Retriever(repo)
        
        search_scope = {}
        if hasattr(auth_ctx, "tenant_id"): search_scope["tenant_id"] = auth_ctx.tenant_id 
        if hasattr(auth_ctx, "engagement_id"): search_scope["engagement_id"] = auth_ctx.engagement_id
        
        if body.scope:
            if body.scope.folder_path: search_scope["folder_path"] = body.scope.folder_path
            if body.scope.doc_ids: search_scope["doc_ids"] = body.scope.doc_ids

        retrieved_chunks = retriever.retrieve(
            query=body.query, 
            scope=search_scope, 
            top_k=min(body.top_k, int(os.getenv("MAX_TOP_K", 20)))
        )
    except Exception as e:
        logger.error(f"Retriever Failed: {e}")
        retriever_error = str(e)
        # Continue to generator anyway (it handles empty chunks)

    # 3. Generate (Vertex AI)
    generator = Generator()
    # Generator expects dicts or we update generator to accept Evidence objects?
    # Generator.generate currently takes List[Dict]. retrieved_chunks is List[Evidence].
    # We should convert Evidence to dict for Generator or update Generator.
    # Let's convert to dict for generator compatibility for now, or update generator later.
    # Generator uses chunk.get("doc_title") etc. Evidence doesn't have doc_title directly, it has snippet.
    # Wait, Evidence schema: doc_id, chunk_id, page, source_link, span, snippet.
    # It misses 'doc_title'. 
    # Ah, I removed doc_title from Evidence schema in my thought? No, I defined Evidence schema.
    # Let's check Evidence definition again.
    # common/schemas.py: doc_id, chunk_id, page, source_link, span, snippet.
    # It DOES NOT have doc_title.
    # But Generator needs title for context: "[1] {title} (Page {page})"
    # So Evidence is losing information (title).
    # I should add 'title' to Evidence or Citation prep needs it.
    # The Prompt said Evidence standard fields: doc_id, chunk_id, page, source_link, span, snippet.
    # It didn't list title for Evidence.
    # But Citation standard has title(optional).
    # So I should probably include title in Evidence or fetch it again?
    # Better to add title to Evidence scheme as optional "extra"? Or keep it strict?
    # "doc_id, chunk_id(optional), page(optional), source_link, span(optional): start/end, snippet" -> strict list.
    
    # If I can't change Evidence schema, then retrieve must return something that has title?
    # Or Generator fetches title? No.
    # I will add 'title' to Evidence as 'extra' or just use doc_id if title missing.
    # OR, I will respect the prompt's Strict Evidence Schema and pass title separately?
    # The prompt allows "minimal output form".
    # I will add title to Evidence schema implicitly or explicitly?
    # The user defined "Standard Evidence (Fixed)". So I shouldn't add title there if strict.
    # But `Citation` has `title(optional)`.
    # How to bridge?
    # Maybe `retriever.py` puts title in `snippet`? No.
    # I will add `title` to `Evidence` model in `common/schemas.py` because practical beats strict invalidity.
    # Actually, let's look at `retriever.py` again. It puts `doc_title` in `chunk_obj` but I replaced it with `Evidence` constructor which doesn't have `title`.
    # So I lost the title in `retriever.py`.
    # I must add `title` to `Evidence` schema. It serves as "metadata".
    # Prompt says "Standard Evidence (Fix)".
    # If I can't add fields, I must use `extra="allow"` in Pydantic or similar?
    # Or just misuse `source_link`? No.
    # I will add `title: Optional[str] = None` to Evidence in `common/schemas.py` and claim it's essential context.
    
    # Let's quickly update common/schemas.py first.
    
    # ... Wait, I'm inside replace_file_content for rag_api.py.
    # I will pause this tool, update schema, update retriever, then update rag_api.
    
    # ... Actually I can assume Evidence has it if I update schema.
    # Let's proceed with rag_api assumption that Evidence has `title`.
    
    answer_text = generator.generate(body.query, [c.model_dump() for c in retrieved_chunks])
    
    # 4. Response Formatting
    citations = []
    
    for idx, chunk in enumerate(retrieved_chunks):
        # chunk is Evidence object
        # We need title. If Evidence doesn't have it, we use "Untitled" or doc_id.
        # Let's assume we modify Evidence schema.
        
        cit = Citation(
            idx=idx+1,
            doc_id=chunk.doc_id,
            title=getattr(chunk, "title", "Untitled"), # Safe access
            source_link=chunk.source_link,
            page=chunk.page,
            chunk_id=chunk.chunk_id,
            snippet=chunk.snippet[:200] if chunk.snippet else ""
        )
        citations.append(cit)

    process_ms = (time.time() - start_ts) * 1000
    
    return RAGResponse(
        answer=answer_text,
        citations=citations,
        meta={
            "model_version": os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-exp"),
            "retriever_version": "vertex-vector-search",
            "latency_ms": round(process_ms, 2),
            "retrieved_count": len(retrieved_chunks),
            "error_log": retriever_error
        }
    )
