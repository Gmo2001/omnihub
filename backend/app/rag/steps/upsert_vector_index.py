import json
import logging
from google.cloud import storage
from google.cloud import firestore
from google.cloud import aiplatform_v1

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.vector_schema import VectorSchema

# Logger
logger = logging.getLogger("VectorIndexUpserter")
logger.setLevel(logging.INFO)

class VectorIndexUpserter:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.location = getattr(settings, "VERTEX_LOCATION", "us-central1")
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        
        self.index_name = getattr(settings, "VECTOR_INDEX_NAME", "") # Must be set
        
        # Vertex Client
        client_options = {"api_endpoint": f"{self.location}-aiplatform.googleapis.com"}
        self.index_client = aiplatform_v1.IndexServiceClient(client_options=client_options)
        self.batch_size = int(getattr(settings, "VECTOR_UPSERT_BATCH_SIZE", 50))

    def load_json_from_gcs(self, gcs_uri: str):
        if not gcs_uri or not gcs_uri.startswith("gs://"): return None
        blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            return json.loads(blob.download_as_text())
        except Exception:
            return None

    def process_single_document(self, doc_id: str):
        if not self.index_name:
            logger.error("SKIP Upsert: VECTOR_INDEX_NAME not set")
            return

        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active"): return

        logger.info(f"📤 [Vector] 업서트 시작: {doc_id}")

        embed_ref = self.db.collection("embeddings").document(doc_id).get()
        if not embed_ref.exists: return
        
        embeddings_data = self.load_json_from_gcs(embed_ref.get("gcs_embeddings_uri"))
        if not embeddings_data: return
        
        embedding_list = embeddings_data.get("embeddings", [])
        if not embedding_list: return
        
        policy_data = self.db.collection("policies").document(doc_id).get()
        policy = policy_data.to_dict() if policy_data.exists else {}
        
        doc_data = self.db.collection("documents").document(doc_id).get()
        doc_meta = doc_data.to_dict() if doc_data.exists else {}

        tenant_id = getattr(settings, "TENANT_ID", "default")
        engagement_id = getattr(settings, "ENGAGEMENT_ID", "default")

        datapoints = []
        for item in embedding_list:
            chunk_id = item.get("chunk_id")
            vector = item.get("vector")
            dp_id = f"{doc_id}::{chunk_id}"
            
            restricts = [
                {"namespace": VectorSchema.TENANT_ID, "allow_list": [tenant_id]},
                {"namespace": VectorSchema.ENGAGEMENT_ID, "allow_list": [engagement_id]},
                {"namespace": VectorSchema.DOC_ID, "allow_list": [doc_id]},
                {"namespace": VectorSchema.SECURITY_LEVEL, "allow_list": [policy.get("security_level", "L1")]},
                {"namespace": VectorSchema.REVIEW_STATUS, "allow_list": [doc_meta.get("review_status", "PENDING")]}
            ]
            
            dp = aiplatform_v1.IndexDatapoint(
                datapoint_id=dp_id,
                feature_vector=vector,
                restricts=restricts
            )
            datapoints.append(dp)
            
        # Batch Upsert
        total_upserted = 0
        try:
            for i in range(0, len(datapoints), self.batch_size):
                batch = datapoints[i : i + self.batch_size]
                req = aiplatform_v1.UpsertDatapointsRequest(
                    index=self.index_name,
                    datapoints=batch
                )
                self.index_client.upsert_datapoints(request=req)
                total_upserted += len(batch)
                
            self.db.collection("vector_upserts").document(doc_id).set({
                "doc_id": doc_id,
                "index_name": self.index_name,
                "upserted_count": total_upserted,
                "timestamp": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            self.db.collection("profiles").document(doc_id).set({
                "process_flags": {"vector_db": False}
            }, merge=True)
            
            logger.info(f"✅ [Vector] 업서트 완료: {total_upserted} points")
            
        except Exception as e:
            logger.error(f"FAIL Vector Upsert: {e}")
            self.db.collection("vector_upserts").document(doc_id).set({
                "doc_id": doc_id,
                "error": str(e),
                "timestamp": firestore.SERVER_TIMESTAMP
            }, merge=True)
