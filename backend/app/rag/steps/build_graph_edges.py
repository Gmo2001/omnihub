import json
import logging
from google.cloud import storage
from google.cloud import firestore

from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("GraphEdgeBuilder")
logger.setLevel(logging.INFO)

class GraphEdgeBuilder:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        self.top_concepts_cap = int(getattr(settings, "TOP_CONCEPTS_CAP", 50))
        self.concept_map = {}
        # Pre-load map or load on demand
        self.load_concept_map()

    def normalize_name(self, name: str) -> str:
        if not name: return ""
        return name.strip().lower()

    def load_concept_map(self):
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        map_id = f"{tenant}__{engagement}"
        map_ref = self.db.collection("concept_maps").document(map_id).get()
        
        if not map_ref.exists:
            logger.info("Concept Map not found (Concepts might not be built yet).")
            return

        gcs_uri = map_ref.get("gcs_uri")
        if not gcs_uri: return
        
        blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            raw = blob.download_as_text()
            self.concept_map = json.loads(raw)
            logger.info(f"Loaded Concept Map: {len(self.concept_map)} entries")
        except Exception as e:
            logger.error(f"Concept Map Load Fail: {e}")

    def load_entities_from_gcs(self, gcs_uri: str):
        if not gcs_uri.startswith("gs://"): return []
        blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            data = json.loads(blob.download_as_text())
            return data.get("entities", [])
        except Exception:
            return []

    def process_single_document(self, doc_id: str):
        if not self.concept_map:
            # Try reloading in case it was built recently
            self.load_concept_map()
            if not self.concept_map:
                logger.warning(f"SKIP Edges {doc_id}: No Concept Map available")
                return

        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active"): return

        logger.info(f"🕸️ [Edges] 엣지 생성: {doc_id}")

        ent_ref = self.db.collection("entities").document(doc_id).get()
        if not ent_ref.exists: return
        
        entities = self.load_entities_from_gcs(ent_ref.get("gcs_entities_uri"))
        content_hash = profile_data.get("doc_content_hash")
        
        batch = self.db.batch()
        batch_count = 0
        concepts_counter = {}

        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")

        for ent in entities:
            raw_name = ent.get("name")
            type_ = ent.get("type", "OTHERS")
            norm_name = self.normalize_name(raw_name)
            map_key = f"{type_}:{norm_name}"
            
            concept_id = self.concept_map.get(map_key)
            if not concept_id: continue # Skip unmapped
            
            edge_id = f"{doc_id}__{concept_id}__mentions"
            evidence = ent.get("evidence", [])
            
            edge_data = {
                "edge_id": edge_id,
                "tenant_id": tenant,
                "engagement_id": engagement,
                "doc_id": doc_id,
                "concept_id": concept_id,
                "edge_type": "mentions",
                "active": True,
                "confidence": 1.0,
                "doc_content_hash": content_hash,
                "mentions_count": len(evidence),
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            batch.set(self.db.collection("edges_doc_concept").document(edge_id), edge_data, merge=True)
            batch_count += 1
            concepts_counter[concept_id] = concepts_counter.get(concept_id, 0) + len(evidence)
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0: batch.commit()
        
        # Document Top Concepts Update (Preliminary, before Ranking)
        sorted_concepts = sorted(concepts_counter.items(), key=lambda x: x[1], reverse=True)
        top_list = [{"concept_id": cid, "count": cnt} for cid, cnt in sorted_concepts[:self.top_concepts_cap]]
        
        self.db.collection("documents").document(doc_id).set({
            "top_concepts": top_list # Ranker will refine this with scores later
        }, merge=True)
        
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"edges": False}
        }, merge=True)
        
        logger.info(f"✅ [Edges] 엣지 생성 완료: {len(concepts_counter)} unique links")
