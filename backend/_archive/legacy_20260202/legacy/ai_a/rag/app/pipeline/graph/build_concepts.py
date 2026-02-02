import os
import json
import logging
import time
import hashlib
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict
from dotenv import load_dotenv

from google.cloud import firestore
from google.cloud import storage

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
    
    RULES_VERSION = os.getenv("CONCEPT_RULES_VERSION", "v1")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.GCS_BUCKET: raise ValueError("GCS_BUCKET 누락")
        if not cls.TENANT_ID or not cls.ENGAGEMENT_ID:
            raise ValueError("TENANT_ID/ENGAGEMENT_ID 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("ConceptBuilder")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class ConceptBuilder:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        
        # State
        self.concept_map = {} # (type, alias) -> concept_id
        self.concepts = {} # concept_id -> ConceptData

    def normalize_name(self, name: str) -> str:
        """이름 정규화: lower(), strip()"""
        if not name: return ""
        return name.strip().lower()

    def generate_concept_id(self, type_: str, canonical_name: str) -> str:
        """concept_id = SHA1(tenant:engagement:type:canonical)"""
        raw = f"{Config.TENANT_ID}:{Config.ENGAGEMENT_ID}:{type_}:{canonical_name}"
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()

    def load_entities_from_gcs(self, gcs_uri: str) -> List[Dict[str, Any]]:
        """GCS에서 엔티티 JSON 로드"""
        if not gcs_uri or not gcs_uri.startswith("gs://"):
            return []
        
        blob_path = gcs_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            data = json.loads(blob.download_as_text())
            return data.get("entities", [])
        except Exception as e:
            logger.warning(f"GCS Entity Load Fail ({gcs_uri}): {e}")
            return []

    def aggregate_entities(self):
        """전체(Scope 내) 엔티티 수집 및 정규화"""
        logger.info("Scanning entities...")
        
        # Scope Filter: documents 컬렉션 기준으로 active=True인 doc_id 수집
        # entities 컬렉션을 직접 스캔하는 것이 효율적일 수 있으나, active check 필요.
        # 여기서는 entities 컬렉션을 돌면서 doc_id를 역추적하거나, profiles에서 entity 포인터를 가져옴.
        
        # profiles -> entities pointer -> load
        profiles = (self.db.collection("profiles")
                    .where("tenant_id", "==", Config.TENANT_ID)
                    .where("engagement_id", "==", Config.ENGAGEMENT_ID)
                    .where(filter=firestore.FieldFilter("active", "==", True))
                    .stream())
        
        # 메모리 효율을 위해 Streaming 처리하며 바로바로 집계
        # { (type, canonical) : { 'aliases': set(), 'doc_ids': set(), 'count': 0 } }
        aggregator = defaultdict(lambda: {'aliases': set(), 'doc_ids': set(), 'count': 0})
        
        count = 0
        for doc in profiles:
            doc_id = doc.id
            # Entity Pointer 확인 (entities/{doc_id})
            ent_ref = self.db.collection("entities").document(doc_id).get()
            if not ent_ref.exists:
                continue
                
            gcs_uri = ent_ref.get("gcs_entities_uri")
            entities = self.load_entities_from_gcs(gcs_uri)
            
            for ent in entities:
                raw_name = ent.get("name")
                type_ = ent.get("type", "OTHERS")
                aliases = ent.get("aliases", [])
                
                if not raw_name: continue
                
                # Canonical 결정 (운영 최소: normalized name)
                # 더 나은 로직: 이미 concept_map에 있으면 그걸 따름?
                # 여기선 일괄 집계 방식(Batch)
                norm_name = self.normalize_name(raw_name)
                
                key = (type_, norm_name)
                aggregator[key]['aliases'].add(raw_name)
                for a in aliases:
                    aggregator[key]['aliases'].add(a)
                
                aggregator[key]['doc_ids'].add(doc_id)
                aggregator[key]['count'] += 1
            
            count += 1
            if count % 10 == 0:
                logger.debug(f"Processed {count} docs...")

        logger.info(f"Aggregation complete. Found {len(aggregator)} unique concepts.")
        return aggregator

    def build_and_save_concepts(self, aggregator):
        """집계된 데이터를 Concept으로 변환 및 저장"""
        logger.info("Building concepts...")
        
        batch = self.db.batch()
        batch_count = 0
        
        concept_map_export = {} # type:alias -> concept_id
        
        for (type_, canonical_norm), data in aggregator.items():
            # Canonical Name 복원 (가장 짧은 것? 가장 빈도 높은 것? 여기선 alias 중 하나 선택)
            # aliases set에서 가장 '대표성' 있는 이름 선택 로직 (간단히: 짧은 것 우선 or 사전순)
            # 여기선 aliases 중 raw_name과 가장 유사하거나, 그냥 정렬해서 첫번째
            aliases_list = sorted(list(data['aliases']))
            canonical_display = aliases_list[0] # 임의 선택
            
            concept_id = self.generate_concept_id(type_, canonical_norm)
            
            concept_data = {
                "concept_id": concept_id,
                "tenant_id": Config.TENANT_ID,
                "engagement_id": Config.ENGAGEMENT_ID,
                "type": type_,
                "canonical_name": canonical_display,
                "aliases": aliases_list,
                "doc_frequency": len(data['doc_ids']),
                "total_occurrence": data['count'],
                "last_seen_at": firestore.SERVER_TIMESTAMP,
                "rules_version": Config.RULES_VERSION,
                "active": True
                # doc_ids 리스트는 너무 클 수 있으므로 제외하거나 별도 서브컬렉션
            }
            
            # Upsert Concept
            ref = self.db.collection("concepts").document(concept_id)
            batch.set(ref, concept_data, merge=True)
            batch_count += 1
            
            # Concept Map 구성
            # 정규화된 이름 -> ID 매핑
            # alias 정규화해서 매핑
            for alias in aliases_list:
                norm_alias = self.normalize_name(alias)
                map_key = f"{type_}:{norm_alias}"
                concept_map_export[map_key] = concept_id
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
                
        if batch_count > 0:
            batch.commit()

        return concept_map_export

    def save_concept_map(self, concept_map):
        """Concept Map을 GCS에 저장 (양이 많으므로)하고 Firestore가 가리킴"""
        logger.info(f"Saving Concept Map ({len(concept_map)} entries)...")
        
        # map_id = tenant__engagement
        map_id = f"{Config.TENANT_ID}__{Config.ENGAGEMENT_ID}"
        gcs_path = f"concept_maps/{map_id}/map.json"
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(
            json.dumps(concept_map, ensure_ascii=False),
            content_type="application/json"
        )
        gcs_uri = f"gs://{Config.GCS_BUCKET}/{gcs_path}"
        
        # Firestore Pointer
        self.db.collection("concept_maps").document(map_id).set({
            "tenant_id": Config.TENANT_ID,
            "engagement_id": Config.ENGAGEMENT_ID,
            "gcs_uri": gcs_uri,
            "entry_count": len(concept_map),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        logger.info("Concept Map Saved.")

    def run(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Build Concepts 작업 시작...")
        
        aggregator = self.aggregate_entities()
        concept_map = self.build_and_save_concepts(aggregator)
        self.save_concept_map(concept_map)
        
        logger.info("작업 완료.")

if __name__ == "__main__":
    builder = ConceptBuilder()
    builder.run()
