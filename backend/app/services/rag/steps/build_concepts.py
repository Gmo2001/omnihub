import hashlib
import json
import logging
import time
from collections import defaultdict
from google.cloud import storage
from google.cloud import firestore

from app.core.config import settings
from app.core.gcp_clients import db

logger = logging.getLogger("ConceptBuilder")
logger.setLevel(logging.INFO)

class ConceptBuilder:
    def __init__(self):
        self.db = db
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        self.rules_version = getattr(settings, "CONCEPT_RULES_VERSION", "v1")

    def normalize_name(self, name: str) -> str:
        if not name: return ""
        return name.strip().lower()

    def generate_concept_id(self, type_: str, canonical_name: str) -> str:
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        raw = f"{tenant}:{engagement}:{type_}:{canonical_name}"
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()

    def load_entities_from_gcs(self, gcs_uri: str):
        if not gcs_uri.startswith("gs://"): return []
        blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            data = json.loads(blob.download_as_text())
            return data.get("entities", [])
        except Exception:
            return []

    def run_batch(self):
        """배치 실행: 전체 활성 문서 스캔 -> 개념 Aggregation"""
        logger.info("Build Concepts Batch Start...")
        
        # Scope Filter can be added here
        docs = self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).stream()
        
        aggregator = defaultdict(lambda: {'aliases': set(), 'doc_ids': set(), 'count': 0})
        count = 0
        
        for doc in docs:
            doc_id = doc.id
            ent_ref = self.db.collection("entities").document(doc_id).get()
            if not ent_ref.exists: continue
            
            gcs_uri = ent_ref.get("gcs_entities_uri")
            entities = self.load_entities_from_gcs(gcs_uri)
            
            for ent in entities:
                raw_name = ent.get("name")
                type_ = ent.get("type", "OTHERS")
                aliases = ent.get("aliases", [])
                
                if not raw_name: continue
                norm_name = self.normalize_name(raw_name)
                
                key = (type_, norm_name)
                aggregator[key]['aliases'].add(raw_name)
                for a in aliases: aggregator[key]['aliases'].add(a)
                aggregator[key]['doc_ids'].add(doc_id)
                aggregator[key]['count'] += 1
            count += 1
            
        # Build Concepts
        batch_count = 0
        batch = self.db.batch()
        concept_map_export = {}
        
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")

        for (type_, canonical_norm), data in aggregator.items():
            aliases_list = sorted(list(data['aliases']))
            canonical_display = aliases_list[0]
            concept_id = self.generate_concept_id(type_, canonical_norm)
            
            concept_data = {
                "concept_id": concept_id,
                "tenant_id": tenant,
                "engagement_id": engagement,
                "type": type_,
                "canonical_name": canonical_display,
                "aliases": aliases_list,
                "doc_frequency": len(data['doc_ids']),
                "total_occurrence": data['count'],
                "last_seen_at": firestore.SERVER_TIMESTAMP,
                "rules_version": self.rules_version,
                "active": True
            }
            
            batch.set(self.db.collection("concepts").document(concept_id), concept_data, merge=True)
            batch_count += 1
            
            for alias in aliases_list:
                norm_alias = self.normalize_name(alias)
                map_key = f"{type_}:{norm_alias}"
                concept_map_export[map_key] = concept_id
                
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
                
        if batch_count > 0: batch.commit()
        
        # Save Map to GCS
        self.save_concept_map(concept_map_export)
        logger.info(f"Concepts Build Complete. Found {len(aggregator)} concepts.")

    def save_concept_map(self, concept_map):
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        map_id = f"{tenant}__{engagement}"
        gcs_path = f"concept_maps/{map_id}/map.json"
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(json.dumps(concept_map, ensure_ascii=False), content_type="application/json")
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        
        self.db.collection("concept_maps").document(map_id).set({
            "tenant_id": tenant,
            "engagement_id": engagement,
            "gcs_uri": gcs_uri,
            "entry_count": len(concept_map),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
