import os
import json
import logging
import time
from typing import Dict, Any, List
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
    
    TOP_CONCEPTS_CAP = int(os.getenv("TOP_CONCEPTS_CAP", 50))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.GCS_BUCKET: raise ValueError("GCS_BUCKET 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("GraphEdgeBuilder")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class GraphEdgeBuilder:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        
        self.concept_map = {}

    def normalize_name(self, name: str) -> str:
        if not name: return ""
        return name.strip().lower()

    def load_concept_map(self):
        """Concept Map 로드 (Firestore -> GCS Pointer)"""
        map_id = f"{Config.TENANT_ID}__{Config.ENGAGEMENT_ID}"
        map_ref = self.db.collection("concept_maps").document(map_id).get()
        
        if not map_ref.exists:
            logger.warning("Concept Map NotFound. build_concepts first?")
            return

        gcs_uri = map_ref.get("gcs_uri")
        if not gcs_uri: 
            return
            
        blob_path = gcs_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            raw = blob.download_as_text()
            self.concept_map = json.loads(raw)
            logger.info(f"Loaded Concept Map: {len(self.concept_map)} entries.")
        except Exception as e:
            logger.error(f"Concept Map Load Failed: {e}")

    def load_entities_from_gcs(self, gcs_uri: str) -> List[Dict[str, Any]]:
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

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile_data = doc_snapshot.to_dict()
        
        # Flag Check
        flags = profile_data.get("process_flags", {})
        if flags.get("edges") is False:
             return

        logger.info(f"Building Edges for {doc_id}...")

        # 1. 문서 엔티티 로드
        ent_ref = self.db.collection("entities").document(doc_id).get()
        if not ent_ref.exists:
            logger.warning("Entities NotFound")
            return
            
        entities = self.load_entities_from_gcs(ent_ref.get("gcs_entities_uri"))
        content_hash = profile_data.get("doc_content_hash")

        # 2. 엣지 생성 (Doc -> Mention -> Concept)
        batch = self.db.batch()
        batch_count = 0
        concepts_counter = {} # concept_id -> count
        
        for ent in entities:
            raw_name = ent.get("name", "")
            type_ = ent.get("type", "OTHERS")
            norm_name = self.normalize_name(raw_name)
            
            # Map Lookup
            map_key = f"{type_}:{norm_name}"
            concept_id = self.concept_map.get(map_key)
            
            if not concept_id:
                # fallback: OTHERS 타입이나 매핑 실패 등
                # 운영 최소: 매핑 안되면 엣지 미생성 (또는 Unmapped Concept 생성?)
                # 여기선 스킵
                continue
                
            # Edge Key: {doc_id}__{concept_id}__mentions
            edge_id = f"{doc_id}__{concept_id}__mentions"
            
            evidence = ent.get("evidence", [])
            # evidence가 많으면 앞부분만? 일단 다 넣음(포인터니까)
            
            edge_data = {
                "edge_id": edge_id,
                "tenant_id": Config.TENANT_ID,
                "engagement_id": Config.ENGAGEMENT_ID,
                "doc_id": doc_id,
                "concept_id": concept_id,
                "edge_type": "mentions",
                "active": True,
                "confidence": 1.0, # Entity Extractor에서 받으면 좋음
                "doc_content_hash": content_hash,
                "mentions_count": len(evidence), # 출현 횟수
                # "evidence": evidence, # 너무 클 수 있으므로 제외하거나 일부만
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            ref = self.db.collection("edges_doc_concept").document(edge_id)
            batch.set(ref, edge_data, merge=True)
            batch_count += 1
            
            # Top Concept 집계용
            concepts_counter[concept_id] = concepts_counter.get(concept_id, 0) + len(evidence)
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()

        # 3. Top Concepts to Document
        # 출현 빈도 순 정렬
        sorted_concepts = sorted(concepts_counter.items(), key=lambda x: x[1], reverse=True)
        top_list = [{"concept_id": cid, "count": cnt} for cid, cnt in sorted_concepts[:Config.TOP_CONCEPTS_CAP]]
        
        self.db.collection("documents").document(doc_id).set({
            "top_concepts": top_list
        }, merge=True)
        
        # 4. Flag Off
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"edges": False}
        }, merge=True)
        
        logger.info(f"SUCCESS {doc_id}: Created {len(concepts_counter)} unique edges.")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Graph Edge Build 작업 시작...")
        
        # Concept Map 1회 로드
        self.load_concept_map()
        if not self.concept_map:
            logger.error("Concept Map이 비어있어 작업을 중단합니다.")
            return

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
    builder = GraphEdgeBuilder()
    builder.run_batch()
