import json
import logging
import time
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("DocBundleMerger")
logger.setLevel(logging.INFO)

class DocBundleMerger:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        self.pipeline_version = getattr(settings, "PIPELINE_VERSION", "v0.1")

    def get_doc_snapshot(self, collection, doc_id):
        doc = self.db.collection(collection).document(doc_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def process_single_document(self, doc_id: str):
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active"): return

        logger.info(f"📦 [Bundle] 병합 시작: {doc_id}")

        # Collect Artifacts
        policy_data = self.get_doc_snapshot("policies", doc_id)
        chunks_meta = self.get_doc_snapshot("chunks", doc_id)
        card_data = self.get_doc_snapshot("cards", doc_id)
        entities_meta = self.get_doc_snapshot("entities", doc_id)
        
        errors = []
        if not policy_data: errors.append("Policy missing")
        if not chunks_meta: errors.append("Chunks missing")
        if not card_data: errors.append("Card missing")
        if not entities_meta: errors.append("Entities missing")
        
        content_hash = profile_data.get("doc_content_hash", "nohash")
        
        bundle = {
            "header": {
                "doc_id": doc_id,
                "tenant_id": getattr(settings, "TENANT_ID", "default"),
                "engagement_id": getattr(settings, "ENGAGEMENT_ID", "default"),
                "doc_content_hash": content_hash,
                "pipeline_version": self.pipeline_version,
                "bundled_at": time.time()
            },
            "profile": profile_data,
            "policy": policy_data,
            "chunks_pointer": chunks_meta,
            "card": card_data,
            "entities_pointer": entities_meta,
            "errors": errors
        }
        
        stage_status = "B_DONE" if not errors else "B_PARTIAL"
        
        # Save Bundle to GCS
        bundle_path = f"bundles/{doc_id}/{content_hash}/bundle.json"
        blob = self.bucket.blob(bundle_path)
        blob.upload_from_string(
            json.dumps(bundle, ensure_ascii=False, default=str), 
            content_type="application/json"
        )
        bundle_uri = f"gs://{self.bucket_name}/{bundle_path}"
        
        # Firestore Update
        bundle_meta = {
            "doc_id": doc_id,
            "doc_content_hash": content_hash,
            "gcs_bundle_uri": bundle_uri,
            "pipeline_version": self.pipeline_version,
            "last_errors": errors,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        batch = self.db.batch()
        batch.set(self.db.collection("doc_bundles").document(doc_id), bundle_meta, merge=True)
        
        batch.set(self.db.collection("documents").document(doc_id), {
            "stage": stage_status,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        batch.set(self.db.collection("profiles").document(doc_id), {
            "process_flags": {"upsert": False}
        }, merge=True)
        
        batch.commit()
        logger.info(f"✅ [Bundle] 병합 완료: {stage_status}")
