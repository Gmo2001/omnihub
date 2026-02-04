import hashlib
import json
import logging
import time
from collections import defaultdict
from google.cloud import storage
from google.cloud import firestore

from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("ConceptBuilder")
logger.setLevel(logging.INFO)

class ConceptBuilder:
    def __init__(self):
        self.db = get_firestore_client()
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

    def process_single_document(self, doc_id: str):
        """
        단일 문서에 대한 Concept Incremental Update
        해당 문서의 엔티티만 처리하여 관련 개념 업데이트
        + Concept Map 생성/업데이트 (Edge 생성을 위해 필수)
        """
        logger.info(f"🧠 [Concept] Incremental update for {doc_id}")
        
        # 1. 해당 문서의 엔티티 조회
        ent_ref = self.db.collection("entities").document(doc_id).get()
        if not ent_ref.exists:
            logger.warning(f"SKIP {doc_id}: No entities found")
            return
            
        gcs_uri = ent_ref.get("gcs_entities_uri")
        entities = self.load_entities_from_gcs(gcs_uri)
        
        if not entities:
            logger.warning(f"SKIP {doc_id}: Empty entities list")
            return
        
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        
        # 2. 기존 Concept Map 로드 (병합을 위해)
        existing_map = self._load_existing_concept_map()
        
        # 3. 엔티티별 개념 생성/업데이트
        batch = self.db.batch()
        batch_count = 0
        processed_concepts = set()
        new_map_entries = {}  # 이번에 추가될 Map 엔트리
        
        for ent in entities:
            raw_name = ent.get("name")
            type_ = ent.get("type", "OTHERS")
            aliases = ent.get("aliases", [])
            
            if not raw_name:
                continue
                
            norm_name = self.normalize_name(raw_name)
            concept_id = self.generate_concept_id(type_, norm_name)
            
            if concept_id in processed_concepts:
                continue
            processed_concepts.add(concept_id)
            
            # 기존 개념 조회
            existing_ref = self.db.collection("concepts").document(concept_id).get()
            
            aliases_set = {raw_name}
            for a in aliases:
                aliases_set.add(a)
            
            if existing_ref.exists:
                # 기존 개념 업데이트 (aliases 병합, doc_frequency 증가)
                existing_data = existing_ref.to_dict()
                existing_aliases = set(existing_data.get("aliases", []))
                merged_aliases = sorted(list(aliases_set | existing_aliases))
                
                # doc_id를 추적하기 위해 별도 필드 또는 증분 업데이트
                concept_data = {
                    "aliases": merged_aliases,
                    "canonical_name": merged_aliases[0],
                    "last_seen_at": firestore.SERVER_TIMESTAMP,
                    "doc_frequency": firestore.Increment(1) if doc_id not in str(existing_data) else existing_data.get("doc_frequency", 1),
                    "total_occurrence": firestore.Increment(1)
                }
                
                # Map 업데이트 (기존 aliases + 새 aliases)
                for alias in merged_aliases:
                    norm_alias = self.normalize_name(alias)
                    map_key = f"{type_}:{norm_alias}"
                    new_map_entries[map_key] = concept_id
            else:
                # 신규 개념 생성
                concept_data = {
                    "concept_id": concept_id,
                    "tenant_id": tenant,
                    "engagement_id": engagement,
                    "type": type_,
                    "canonical_name": raw_name,
                    "aliases": sorted(list(aliases_set)),
                    "doc_frequency": 1,
                    "total_occurrence": 1,
                    "last_seen_at": firestore.SERVER_TIMESTAMP,
                    "rules_version": self.rules_version,
                    "active": True
                }
                
                # Map 추가 (신규 개념의 모든 aliases)
                for alias in sorted(list(aliases_set)):
                    norm_alias = self.normalize_name(alias)
                    map_key = f"{type_}:{norm_alias}"
                    new_map_entries[map_key] = concept_id
            
            batch.set(self.db.collection("concepts").document(concept_id), concept_data, merge=True)
            batch_count += 1
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()
        
        # 4. Concept Map 병합 및 저장
        merged_map = {**existing_map, **new_map_entries}
        self.save_concept_map(merged_map)
        
        logger.info(f"✅ [Concept] Updated {len(processed_concepts)} concepts for {doc_id}")
        logger.info(f"   📊 Concept Map: {len(new_map_entries)} new entries, {len(merged_map)} total")
    
    def _load_existing_concept_map(self) -> dict:
        """기존 Concept Map 로드 (없으면 빈 dict 반환)"""
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        map_id = f"{tenant}__{engagement}"
        
        try:
            map_ref = self.db.collection("concept_maps").document(map_id).get()
            if not map_ref.exists:
                return {}
            
            gcs_uri = map_ref.get("gcs_uri")
            if not gcs_uri:
                return {}
            
            blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
            blob = self.bucket.blob(blob_path)
            raw = blob.download_as_text()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to load existing concept map: {e}")
            return {}

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
