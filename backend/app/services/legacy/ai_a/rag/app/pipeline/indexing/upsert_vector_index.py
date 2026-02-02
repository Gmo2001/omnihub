import os
import json
import logging
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

from google.cloud import firestore
from google.cloud import storage
from google.cloud import aiplatform_v1
from app.common.vector_schema import VectorSchema

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
    
    VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
    VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME") # Resource Name
    # Upsert는 IndexServiceClient를 통해 Index 리소스에 직접 수행 (Streaming Upsert)
    
    VECTOR_DIM = int(os.getenv("VECTOR_DIM", 768))
    BATCH_SIZE = int(os.getenv("VECTOR_UPSERT_BATCH_SIZE", 50))
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.VECTOR_INDEX_NAME: raise ValueError("VECTOR_INDEX_NAME 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("VectorUpserter")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class VectorIndexUpserter:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        
        # Vertex AI Index Client options
        client_options = {"api_endpoint": f"{Config.VERTEX_LOCATION}-aiplatform.googleapis.com"}
        self.index_client = aiplatform_v1.IndexServiceClient(client_options=client_options)

    def load_json_from_gcs(self, gcs_uri: str) -> Any:
        if not gcs_uri or not gcs_uri.startswith("gs://"): return None
        blob_path = gcs_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        return json.loads(blob.download_as_text())

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile_data = doc_snapshot.to_dict()
        
        # Flag Check (upsert 단계)
        flags = profile_data.get("process_flags", {})
        if flags.get("vector_db") is False:
             return

        logger.info(f"Upserting Vector {doc_id}...")

        # 1. 문서 메타데이터 로드
        embed_ref = self.db.collection("embeddings").document(doc_id).get()
        if not embed_ref.exists:
            logger.warning("Embeddings meta missing")
            return
            
        gcs_uri = embed_ref.get("gcs_embeddings_uri")
        embeddings_data = self.load_json_from_gcs(gcs_uri)
        if not embeddings_data:
            logger.warning("Embeddings GCS data missing")
            return

        embedding_list = embeddings_data.get("embeddings", [])
        if not embedding_list:
            logger.warning("Embedding list empty")
            return

        # Policy & Doc Status
        policy_data = self.db.collection("policies").document(doc_id).get()
        policy = policy_data.to_dict() if policy_data.exists else {}
        
        doc_data = self.db.collection("documents").document(doc_id).get()
        doc_meta = doc_data.to_dict() if doc_data.exists else {}

        # 2. Datapoint 변환
        datapoints = []
        for item in embedding_list:
            chunk_id = item.get("chunk_id")
            vector = item.get("vector")
            
            # Datapoint ID: {doc_id}::{chunk_id}
            dp_id = f"{doc_id}::{chunk_id}"
            
            # Metadata (Restricts & Crowding)
            restricts = [
                {"namespace": VectorSchema.TENANT_ID, "allow_list": [Config.TENANT_ID]},
                {"namespace": VectorSchema.ENGAGEMENT_ID, "allow_list": [Config.ENGAGEMENT_ID]},
                {"namespace": VectorSchema.DOC_ID, "allow_list": [doc_id]},
                {"namespace": VectorSchema.SECURITY_LEVEL, "allow_list": [policy.get("security_level", "L1")]},
                {"namespace": VectorSchema.REVIEW_STATUS, "allow_list": [doc_meta.get("review_status", "PENDING")]},
                # Optional
                {"namespace": VectorSchema.CONTENT_HASH, "allow_list": [profile_data.get("doc_content_hash", "nohash")]}
            ]
            
            # Datapoint Field
            dp = aiplatform_v1.IndexDatapoint(
                datapoint_id=dp_id,
                feature_vector=vector,
                restricts=restricts
            )
            datapoints.append(dp)

        # 3. Batch Upsert
        total_upserted = 0
        try:
            for i in range(0, len(datapoints), Config.BATCH_SIZE):
                batch = datapoints[i : i + Config.BATCH_SIZE]
                
                req = aiplatform_v1.UpsertDatapointsRequest(
                    index=Config.VECTOR_INDEX_NAME,
                    datapoints=batch
                )
                self.index_client.upsert_datapoints(request=req)
                total_upserted += len(batch)
                
            logger.info(f"SUCCESS {doc_id}: Upserted {total_upserted} vectors.")
            
            # 4. Result Logging
            self.db.collection("vector_upserts").document(doc_id).set({
                "doc_id": doc_id,
                "index_name": Config.VECTOR_INDEX_NAME,
                "upserted_count": total_upserted,
                "timestamp": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            # 5. Flag Off
            # vector_db 플래그 OFF
            self.db.collection("profiles").document(doc_id).set({
                "process_flags": {"vector_db": False}
            }, merge=True)
            
        except Exception as e:
            logger.error(f"FAIL {doc_id}: Vector Upsert Error: {e}")
            # 일부 실패시 부분 저장? 일단 전체 실패 처리
            self.db.collection("vector_upserts").document(doc_id).set({
                "doc_id": doc_id,
                "error": str(e),
                "timestamp": firestore.SERVER_TIMESTAMP
            }, merge=True)

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Vector Index Upsert 작업 시작...")
        
        docs = list(self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).get())
        
        count = 0
        for doc in docs:
            try:
                self.process_document(doc)
                count += 1
            except Exception as e:
                logger.error(f"FAIL {doc.id}: {e}")
                
        logger.info(f"작업 완료. 총 {count}개 문서 처리.")

if __name__ == "__main__":
    upserter = VectorIndexUpserter()
    upserter.run_batch()
