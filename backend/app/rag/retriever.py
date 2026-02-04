import os
import logging
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel  # Or use your preferred client
from app.services.firestore_repo import FirestoreRepo
from app.common.schemas import Evidence

# (실제 구현 시 RAGScope 모델은 rag_api.py와 공유 필요. 여기선 Dict로 처리)

logger = logging.getLogger("Retriever")

# --- Env Config ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
INDEX_ENDPOINT_NAME = os.getenv("VECTOR_INDEX_ENDPOINT") # projects/.../indexEndpoints/...
DEPLOYED_INDEX_ID = os.getenv("VECTOR_DEPLOYED_INDEX_ID")
EMBED_MODEL_NAME = os.getenv("VERTEX_EMBED_MODEL", "text-embedding-004")

# Tuning Params
TOPK_MULT = int(os.getenv("RETRIEVER_TOPK_MULT", 3))
PER_DOC_CAP = int(os.getenv("PER_DOC_CHUNK_CAP", 2))

class RetrievedChunk(BaseModel):
    doc_id: str
    chunk_id: str
    score: float
    text: str # snippet
    page: Optional[int] = 1
    doc_title: Optional[str] = None
    source_link: Optional[str] = None
    security_level: Optional[str] = None
    
class Retriever:
    def __init__(self, repo: FirestoreRepo):
        self.repo = repo
        
        # Initialize Vertex AI
        # Force credentials if available in settings
        from google.oauth2 import service_account
        from app.core.config import settings
        
        creds = None
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
             creds = service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)

        aiplatform.init(project=PROJECT_ID, location=LOCATION, credentials=creds)
        self.idx_client = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=INDEX_ENDPOINT_NAME)
        self.embed_model = TextEmbeddingModel.from_pretrained(EMBED_MODEL_NAME)

    def _embed_query(self, query: str) -> List[float]:
        try:
            embeddings = self.embed_model.get_embeddings([query])
            return embeddings[0].values
        except Exception as e:
            logger.error(f"Embedding Generation Failed: {e}")
            raise

    def retrieve(self, query: str, scope: Any = None, top_k: int = 5) -> List[Evidence]:
        """
        Main Retrieval Pipeline
        1. Embed Query
        2. Vector Search (with filters)
        3. Post-Processing (Dedup, Diversity, Meta Injection)
        """
        # 1. Embed
        query_vec = self._embed_query(query)
        
        # 2. Build Filter
        # Strict Filters: Tenant/Engagement/Review/Active
        fileters = [
            # Namespace concept (Key: Value)
            # upsert_vector_index.py에서 namespace 설정을 어떻게 했는지 중요
            # 여기서는 Namespace object filter 사용 가정
            # Namespace("tenant_id", self.repo.tenant_id), ...
        ]
        
        # Note: aiplatform SDK find_neighbors filter structure depends on version
        # 여기서는 "Restricts" list of Namespace objects 라고 가정.
        # 실제로는 [Namespace(name="tenant_id", allow_tokens=[tid]), ...] 형태
        
        from google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint import Namespace
        from app.common.vector_schema import VectorSchema
        
        # Base Restricts (Tenant/Engagement/Review Status)
        # [DEBUG] Disable all filters to debug search 0 results
        restricts = []
        # restricts = [
        #     Namespace(VectorSchema.TENANT_ID, [self.repo.tenant_id]),
        #     Namespace(VectorSchema.ENGAGEMENT_ID, [self.repo.engagement_id]),
        #     
        #     # 운영 최소: APPROVED 문서만 검색 (Draft는 검색 제외)
        #     # 만약 Admin이 Draft 검색 원하면 별도 로직 필요 (여기선 운영 최소 규격 강제)
        #     Namespace(VectorSchema.REVIEW_STATUS, ["APPROVED", "PENDING"]),
        # ]
        
        # Scope Filter (Optional)
        # Assuming scope is a dict or object with doc_ids list
        # We need to handle `scope` being RAGScope object OR dict from rag_api.py
        
        scope_doc_ids = []
        if scope:
            if isinstance(scope, dict):
                scope_doc_ids = scope.get("doc_ids", [])
            elif hasattr(scope, "doc_ids"):
                 scope_doc_ids = scope.doc_ids
        
        if scope_doc_ids:
            restricts.append(Namespace(VectorSchema.DOC_ID, scope_doc_ids))
        
        # 3. Search
        # fetch more (TOPK_MULT) to allow filtering/diversity
        search_k = top_k * TOPK_MULT
        
        try:
            neighbors = self.idx_client.find_neighbors(
                deployed_index_id=DEPLOYED_INDEX_ID,
                queries=[query_vec],
                num_neighbors=search_k,
                filter=restricts if restricts else None 
            )
        except Exception as e:
            logger.error(f"Vector Search Failed: {e}")
            # Mock fallback if VS unavailable in local/test
            return []

        if not neighbors: 
            return []
            
        # Neighbors list of list (batch query support)
        result_candidates = neighbors[0] # Single query
        
        # 4. Post-Processing & Meta Injection
        final_chunks: List[Evidence] = []
        doc_counter = {} # Diversity Cap
        
        # Need to fetch doc meta for chunks
        # DB Query Optimization: Collect distinct doc_ids
        # But wait, chunk metadata (snippet, page) might be in Datapoint ID or need separate fetch?
        # Option A: Chunk ID -> Firestore 'chunks' collection fetch (More precise)
        # Option B: Metadata embedded in vector index (Fastest, but size limit)
        # 운영 최소: ID가 `docId_chunkId` 포맷, snippet은 별도 조회 필요
        
        # Batch Fetch logic (simplified)
        for match in result_candidates:
            # match.id format: docId::chunkId (from upsert script)
            composite_id = match.id
            
            if "::" in composite_id:
                doc_id, chunk_id = composite_id.split("::") # split both parts
            else:
                continue
            
            # Diversity Check
            if doc_counter.get(doc_id, 0) >= PER_DOC_CAP:
                continue
            
            # 5. Fetch Meta & Content
            # Cache doc meta to avoid redundant calls
            # Use self.repo.get_document(doc_id)
            doc_meta = self.repo.get_document(doc_id)
            if not doc_meta: continue # Maybe deleted or permission denied
            
            # [Immediate Search Filtering] active=False check
            # Vector Index Update Delay를 보완하기 위해 메타에서 직접 체크
            if not doc_meta.get("active", True):
                continue
            
            # Review Status Check (Optional but safe)
            # if doc_meta.get("review_status") != "APPROVED": continue
            
            # Fetch Chunk Content from Firestore 'chunks' collection
            try:
                # 3. GCS Download (On-Demand)
                # 문서당 한 번만 다운로드하면 됨 (chunk 여러 개여도)
                gcs_chunks = self._fetch_gcs_chunks(doc_id, doc_meta)
                target_chunk = next((c for c in gcs_chunks if c.get("chunk_id") == chunk_id), None)
                snippet = target_chunk.get("text", "") if target_chunk else "Content not found."
                page_num = target_chunk.get("page_start_no", 1) if target_chunk else 1
                if target_chunk and "page" in target_chunk: # Fallback
                     page_num = target_chunk["page"]

            except Exception as e:
                logger.warning(f"Fetch Content Failed: {e}")
                snippet = f"Content retrieval failed: {str(e)}"
                page_num = 1
            
            # Construct Evidence Object
            evidence = Evidence(
                doc_id=doc_id,
                chunk_id=chunk_id, # Original chunk_id (not composite)
                page=page_num,
                source_link=doc_meta.get("source_link"),
                snippet=snippet[:500], # Cap length for safety
                span=None, # Span info not readily available in simple retrieval
                title=doc_meta.get("title", "Untitled")
            )
            
            final_chunks.append(evidence)
            doc_counter[doc_id] = doc_counter.get(doc_id, 0) + 1
            
            if len(final_chunks) >= top_k:
                break
                
        return final_chunks

    def _fetch_gcs_chunks(self, doc_id: str, doc_meta: Dict) -> List[Dict]:
        # Helper to fetch chunks from GCS
        # Optimization: This is slow. Ideally text should be in Firestore or Vector Metadata.
        try:
            # 1. Check if 'chunks' collection has GCS URI
            chunk_ref = self.repo.get_firestore_client().collection("chunks").document(doc_id).get()
            if not chunk_ref.exists: return []
            
            gcs_uri = chunk_ref.get("gcs_chunks_uri")
            if not gcs_uri: return []
            
            # 2. Download from GCS
            from google.cloud import storage
            storage_client = storage.Client(project=PROJECT_ID)
            
            # gs://bucket/path -> bucket, path
            parts = gcs_uri.replace("gs://", "").split("/", 1)
            bucket = storage_client.bucket(parts[0])
            blob = bucket.blob(parts[1])
            
            import json
            content = blob.download_as_text()
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"GCS Fetch Error: {e}")
            return []
