# app/main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import traceback
import random

from .models import ChatRequest, ChatResponse, InitialDataResponse, EvidenceGraphResponse, Citation
from .firestore_repo import (
    get_client, health_check, list_docs, list_concepts,
    get_chunks_by_ids, get_docs_by_ids, get_concepts_by_ids
)
from .vector_search import VectorSearchClient
from .rag_gemini import answer_with_citations
from .embeddings import embed_query
from .config import COL_CHUNKS

app = FastAPI(title="OmniHub Prototype Backend", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_fs = None
_vs = None

@app.on_event("startup")
def startup():
    global _fs, _vs
    try:
        _fs = get_client()
        status = health_check(_fs)
        print(f"Firestore Health: {status}")
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Firestore startup failed: {e}")

    try:
        _vs = VectorSearchClient()
        print("Vector Search Client initialized.")
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"VectorSearch startup failed: {e}")

@app.get("/api/initial-data", response_model=InitialDataResponse)
def api_initial_data():
    try:
        docs = list_docs(_fs, limit=4000)
        concepts = list_concepts(_fs, limit=8000)
        return {"docs": docs, "concepts": concepts}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def _apply_filters_on_chunks(chunks, filters):
    if not filters:
        return chunks
    out = []
    for c in chunks:
        if filters.securityLevel and c.get("securityLevel") != filters.securityLevel:
            continue
        if filters.department and c.get("department") != filters.department:
            continue
        if filters.fileIds:
            if c.get("parent_doc_id") not in set(filters.fileIds):
                continue
        out.append(c)
    return out

@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    try:
        # Debug logging to file
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"\n========== NEW REQUEST ==========\n")
            f.write(f"Query: {req.question}\n")
        
        query_embedding = embed_query(req.question)
        
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"Embedding dim: {len(query_embedding)}\n")
        
        if _vs:
            chunk_ids = _vs.find_topk(query_embedding, req.topK)
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"Vector Search returned {len(chunk_ids)} chunk IDs: {chunk_ids[:3] if chunk_ids else []}\n")
            
            chunks = get_chunks_by_ids(_fs, chunk_ids)
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"Firestore returned {len(chunks)} chunks\n")
        else:
            chunks = []
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write("Vector Search client is None!\n")
        
        # FALLBACK: If Vector Search returned nothing, sample diverse chunks from Firestore
        if len(chunks) == 0:
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write("FALLBACK: Sampling diverse chunks from Firestore\n")
            
            # Strategy: Collect more chunks then randomly shuffle for diversity
            all_candidates = []
            
            # Collect a larger pool of chunks
            for doc in _fs.collection(COL_CHUNKS).limit(50).stream():
                d = doc.to_dict() or {}
                d.setdefault("chunk_id", doc.id)
                all_candidates.append(d)
            
            # Shuffle to randomize
            random.shuffle(all_candidates)
            
            # Take diverse samples (one per document)
            sample_chunks = []
            seen_docs = set()
            
            for d in all_candidates:
                parent_doc = d.get("parent_doc_id", "")
                
                # Skip if we already have a chunk from this document
                if parent_doc in seen_docs:
                    continue
                    
                sample_chunks.append(d)
                seen_docs.add(parent_doc)
                
                # Stop when we have enough
                if len(sample_chunks) >= req.topK:
                    break
            
            chunks = sample_chunks
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"Sampled {len(chunks)} chunks from {len(seen_docs)} different documents\n")
            
        chunks = _apply_filters_on_chunks(chunks, req.filters)
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"After filters: {len(chunks)} chunks\n")
        
        answer_text = answer_with_citations(req.question, chunks)

        citations = []
        for c in chunks:
            citations.append(Citation(
                chunk_id=c.get("chunk_id", ""),
                doc_id=c.get("parent_doc_id", ""),
                page=c.get("page", 1),
                source_uri=c.get("source_uri", "") or c.get("sourceUri", ""),
                snippet=c.get("snippet", "") or c.get("content", "")[:200]
            ))

        return ChatResponse(answer=answer_text, citations=citations)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph/evidence", response_model=EvidenceGraphResponse)
def api_graph_evidence(
    question: str = Query(..., min_length=1),
    topK: int = Query(8, ge=1, le=30),
):
    try:
        query_embedding = embed_query(question)
        if _vs:
            chunk_ids = _vs.find_topk(query_embedding, topK)
            chunks = get_chunks_by_ids(_fs, chunk_ids)
        else:
            chunks = []
            
        doc_ids = list(set([c.get("parent_doc_id") for c in chunks if c.get("parent_doc_id")]))
        docs = get_docs_by_ids(_fs, doc_ids)

        concept_ids = set()
        for d in docs:
            tags = d.get("tags")
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, str): concept_ids.add(t)
            cids = d.get("conceptIds")
            if isinstance(cids, list):
                for cid in cids:
                    if isinstance(cid, str): concept_ids.add(cid)

        concepts = get_concepts_by_ids(_fs, list(concept_ids))

        citations = []
        for c in chunks:
            citations.append(Citation(
                chunk_id=c.get("chunk_id", ""),
                doc_id=c.get("parent_doc_id", ""),
                page=c.get("page", 1),
                source_uri=c.get("source_uri", "") or c.get("sourceUri", ""),
                snippet=c.get("snippet", "") or c.get("content", "")[:200]
            ))

        return EvidenceGraphResponse(docs=docs, concepts=concepts, citations=citations)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/docs/{doc_id}/chunks")
def api_doc_chunks(doc_id: str):
    try:
        from .firestore_repo import get_chunks_by_doc_id
        chunks = get_chunks_by_doc_id(_fs, doc_id)
        # Sort by page then chunk_index if available
        # chunk_index might not exist, default to 0
        chunks.sort(key=lambda x: (x.get("page", 1), x.get("chunk_index", 0)))
        return {"chunks": chunks}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
