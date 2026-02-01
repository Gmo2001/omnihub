import os
import json
import logging
import time
import hashlib
from typing import Dict, Any, List
from dotenv import load_dotenv

from google.cloud import firestore
from google.cloud import storage
import vertexai
from vertexai.language_models import TextEmbeddingModel

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    GCS_PREFIX = os.getenv("GCS_PREFIX", "omnihub")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "vertex").lower()
    VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
    VERTEX_EMBED_MODEL = os.getenv("VERTEX_EMBED_MODEL", "text-embedding-004")
    MODEL_VERSION = os.getenv("EMBED_MODEL_VERSION", "v1")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.GCS_BUCKET: raise ValueError("GCS_BUCKET 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("EmbedChunks")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Embedding Wrapper ---
class EmbeddingClient:
    def __init__(self):
        if Config.EMBEDDING_PROVIDER == "vertex":
            vertexai.init(project=Config.PROJECT_ID, location=Config.VERTEX_LOCATION)
            self.model = TextEmbeddingModel.from_pretrained(Config.VERTEX_EMBED_MODEL)
            self.batch_size = 5 # Vertex Embedding Batch Limit (보통 5~20 사이)
        else:
            raise NotImplementedError(f"Provider {Config.EMBEDDING_PROVIDER} not implemented.")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # 모델의 배치를 준수하여 분할 요청
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                embeddings = self.model.get_embeddings(batch)
                all_embeddings.extend([e.values for e in embeddings])
            except Exception as e:
                logger.error(f"Embedding Batch Error: {e}")
                # 실패 시 빈 벡터? 아니면 재시도? 여기선 0 벡터 or Skip
                # 운영상 에러나면 해당 chunk는 제외될 수 있음
                # 여기선 에러 발생 시 그냥 raise하여 해당 문서 실패 처리 (안전)
                raise e
        return all_embeddings

# --- Core Logic ---
class ChunkEmbedder:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        self.embedder = EmbeddingClient()

    def load_json_from_gcs(self, gcs_uri: str) -> Any:
        if not gcs_uri or not gcs_uri.startswith("gs://"): return None
        blob_path = gcs_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        return json.loads(blob.download_as_text())

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile_data = doc_snapshot.to_dict()
        
        # Flag Check
        flags = profile_data.get("process_flags", {})
        if flags.get("embeddings") is False:
             return

        logger.info(f"Embedding {doc_id}...")

        # 1. 문서 메타 및 청크 로드
        # active 상태는 where절에서 이미 걸렀다고 가정
        chunks_meta = self.db.collection("chunks").document(doc_id).get()
        if not chunks_meta.exists:
            logger.warning("Chunks meta missing")
            return
            
        chunks = self.load_json_from_gcs(chunks_meta.get("gcs_chunks_uri"))
        if not chunks:
            logger.warning("Chunks empty")
            return
            
        # 정책 정보 로드 (Security, SSOT)
        policy_data = self.db.collection("policies").document(doc_id).get()
        policy = policy_data.to_dict() if policy_data.exists else {}
        
        # 2. 임베딩 대상 텍스트 추출
        # title, text, table content 등
        target_chunks = []
        texts_to_embed = []
        
        for c in chunks:
            chunk_text = c.get("text", "")
            if not chunk_text.strip(): continue
            
            # 메타데이터 구성 준비
            meta = {
                "tenant_id": Config.TENANT_ID,
                "engagement_id": Config.ENGAGEMENT_ID,
                "doc_id": doc_id,
                "chunk_id": c.get("chunk_id"),
                "doc_content_hash": profile_data.get("doc_content_hash"),
                "security_level": policy.get("security_level", "L1"),
                "ssot_level": policy.get("ssot_level", "Draft"),
                "page_no": c.get("page_start_no"),
                "source_uri": profile_data.get("source_uri"), 
                "chunk_type": c.get("type", "text")
            }
            
            target_chunks.append({"meta": meta, "text": chunk_text})
            texts_to_embed.append(chunk_text)

        if not texts_to_embed:
            logger.warning("No texts to embed")
            return

        # 3. 임베딩 생성 (Batch)
        logger.info(f"Target Chunks: {len(texts_to_embed)}")
        vectors = self.embedder.embed_batch(texts_to_embed)
        
        # 4. 결과 병합
        embedded_result = []
        for item, vec in zip(target_chunks, vectors):
            embedded_result.append({
                "chunk_id": item["meta"]["chunk_id"],
                "vector": vec,
                "metadata": item["meta"],
                "text_snippet": item["text"][:200] # 디버깅용 일부 텍스트 (Option)
            })

        # 5. GCS 저장 (Vector)
        content_hash = profile_data.get("doc_content_hash")
        embed_path = f"embeddings/{doc_id}/{content_hash}/embeddings.json"
        
        payload = {
            "doc_id": doc_id,
            "embeddings": embedded_result,
            "count": len(embedded_result),
            "model_version": Config.VERTEX_EMBED_MODEL,
            "pipeline_version": Config.MODEL_VERSION,
            "created_at": time.time()
        }
        
        blob = self.bucket.blob(embed_path)
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False),
            content_type="application/json"
        )
        gcs_uri = f"gs://{Config.GCS_BUCKET}/{embed_path}"
        
        # 6. Firestore Pointer
        self.db.collection("embeddings").document(doc_id).set({
            "doc_id": doc_id,
            "gcs_embeddings_uri": gcs_uri,
            "count": len(embedded_result),
            "model_version": Config.VERTEX_EMBED_MODEL,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # 7. Flag Off
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"embeddings": False}
        }, merge=True)
        
        logger.info(f"SUCCESS {doc_id}: Embedded {len(embedded_result)} chunks.")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Embed Chunks 작업 시작...")
        
        docs = list(self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).get())
        
        count = 0
        for doc in docs:
            try:
                self.process_document(doc)
                count += 1
            except Exception as e:
                logger.error(f"FAIL {doc.id}: {e}")
                import traceback
                traceback.print_exc()
                
        logger.info(f"작업 완료. 총 {count}개 문서 임베딩.")

if __name__ == "__main__":
    embedder = ChunkEmbedder()
    embedder.run_batch()
