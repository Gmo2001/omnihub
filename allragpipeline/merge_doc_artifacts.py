import os
import json
import logging
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from google.cloud import firestore
from google.cloud import storage

# 로컬 환경 변수 로드
load_dotenv()

if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    GCS_PREFIX = os.getenv("GCS_PREFIX", "omnihub")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "v0.1")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.GCS_BUCKET: raise ValueError("GCS_BUCKET 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("DocBundleMerger")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class DocBundleMerger:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)

    def get_doc_snapshot(self, collection, doc_id):
        doc = self.db.collection(collection).document(doc_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile_data = doc_snapshot.to_dict()
        
        # 필터: active=True
        if not profile_data.get("active"):
            return

        # 깃발 확인: upsert 단계가 필요할 때만 실행 (Optional)
        flags = profile_data.get("process_flags", {})
        if flags.get("upsert") is False:
             # 재처리 강제가 아니면 스킵 가능
             # logger.debug(f"SKIP {doc_id}: Already Bundled")
             return

        logger.info(f"Bundling {doc_id}...")
        
        # 1. 모든 Step의 결과 수집
        policy_data = self.get_doc_snapshot("policies", doc_id)
        chunks_meta = self.get_doc_snapshot("chunks", doc_id)
        card_data = self.get_doc_snapshot("cards", doc_id)
        entities_meta = self.get_doc_snapshot("entities", doc_id)
        
        errors = []
        if not policy_data: errors.append("Policy missing")
        if not chunks_meta: errors.append("Chunks missing")
        # card, entities는 옵션일 수도 있음 (정책에 따라 다름)
        # 하지만 B-Part 전체 완료를 가정하므로 경고 추가
        if not card_data: errors.append("Card missing")
        if not entities_meta: errors.append("Entities missing")
        
        # 2. Bundle 객체 생성
        content_hash = profile_data.get("doc_content_hash")
        
        bundle = {
            "header": {
                "doc_id": doc_id,
                "tenant_id": Config.TENANT_ID,
                "engagement_id": Config.ENGAGEMENT_ID,
                "doc_content_hash": content_hash,
                "pipeline_version": Config.PIPELINE_VERSION,
                "bundled_at": time.time()
            },
            "profile": profile_data, # 전체 포함 or 핵심만 포함
            "policy": policy_data,
            "chunks_pointer": chunks_meta, # GCS URI 포함
            "card": card_data,
            "entities_pointer": entities_meta, # GCS URI 포함
            "errors": errors
        }
        
        stage_status = "B_DONE" if not errors else "B_PARTIAL"
        
        # 3. GCS 저장 (Full Bundle)
        # gs://{bucket}/bundles/{doc_id}/{hash}/bundle.json
        bundle_path = f"bundles/{doc_id}/{content_hash}/bundle.json"
        blob = self.bucket.blob(bundle_path)
        blob.upload_from_string(
            json.dumps(bundle, ensure_ascii=False, default=str), 
            content_type="application/json"
        )
        bundle_uri = f"gs://{Config.GCS_BUCKET}/{bundle_path}"
        
        # 4. Firestore 저장 (Lightweight Pointer)
        bundle_meta = {
            "doc_id": doc_id,
            "doc_content_hash": content_hash,
            "gcs_bundle_uri": bundle_uri,
            "pipeline_version": Config.PIPELINE_VERSION,
            "last_errors": errors,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        batch = self.db.batch()
        
        # doc_bundles/{doc_id}
        batch.set(self.db.collection("doc_bundles").document(doc_id), bundle_meta, merge=True)
        
        # documents/{doc_id} (Status Update)
        batch.set(self.db.collection("documents").document(doc_id), {
            "stage": stage_status,
            "updated_at": firestore.SERVER_TIMESTAMP,
            # 에러가 있으면 review_status를 'ERROR'로? 아니면 유지?
            # 여기선 stage로 판단
        }, merge=True)
        
        # profiles/{doc_id} (Flag Off)
        batch.set(self.db.collection("profiles").document(doc_id), {
            "process_flags": {"upsert": False} # B-Part 마지막이므로 upsert flag off
        }, merge=True)
        
        batch.commit()
        logger.info(f"SUCCESS {doc_id} [{stage_status}]")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Doc Bundle Merge 작업 시작...")
        
        docs = list(self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).get())
        
        count = 0
        for doc in docs:
            try:
                self.process_document(doc)
                count += 1
            except Exception as e:
                logger.error(f"FAIL {doc.id}: {e}")
                
        logger.info(f"작업 완료. 총 {count}개 문서 병합.")

if __name__ == "__main__":
    merger = DocBundleMerger()
    merger.run_batch()
