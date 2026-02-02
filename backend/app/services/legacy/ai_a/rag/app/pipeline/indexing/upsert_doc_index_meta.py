import os
import time
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv
from app.common.enums import SecurityLevel, SSoTLevel, ReviewStatus

from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    DOC_INDEX_VERSION = os.getenv("DOC_INDEX_VERSION", "v1")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("DocIndexUpserter")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class DocIndexUpserter:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.concept_cache = {} # concept_id -> canonical_name (옵션)

    def load_concepts_name(self, concept_ids: List[str]) -> Dict[str, str]:
        # Top Concepts 이름 resolving (필요시)
        # 운영 최소: 그냥 ID만? 프론트가 id->name resolving? 
        # 여기선 간단히 캐싱 없이(또는 on-demand) 읽거나, Edge Ranker 단계에서 name을 박아놨으면 편함.
        # 문서 Top Concepts에는 보통 ID만 있으므로, 필요하면 concepts 컬렉션 조회
        # 성능상 생략하거나, 필요한 경우 bulk load 권장. 이번엔 생략(ID만)
        return {}

    def get_dict(self, collection: str, doc_id: str) -> Dict[str, Any]:
        ref = self.db.collection(collection).document(doc_id).get()
        return ref.to_dict() if ref.exists else {}

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile_data = doc_snapshot.to_dict()
        
        # Flag Check
        flags = profile_data.get("process_flags", {})
        if flags.get("index_meta") is False:
             return

        logger.info(f"Indexing Document {doc_id}...")

        # 1. 산출물 모으기
        # profiles는 이미 있음 (profile_data)
        card_data = self.get_dict("cards", doc_id)
        policy_data = self.get_dict("policies", doc_id)
        # doc_bundles_data = self.get_dict("doc_bundles", doc_id)
        
        # documents 컬렉션 현재 상태 (Review Status 유지 위해)
        current_doc = self.get_dict("documents", doc_id)
        
        # Change Detection (Content Update)
        # build_profile에서 index_meta=True를 켰으므로 여기까지 옴.
        # 실제 내용 변경인지 확인하려면 hash 비교.
        current_hash = current_doc.get("doc_content_hash")
        new_hash = profile_data.get("doc_content_hash")
        
        is_content_changed = (current_hash != new_hash) if current_doc else True # New doc = changed
        
        # Review Status Logic
        # 1. New Doc -> PENDING (or DRAFT based on policy) - here Default PENDING
        # 2. Changed Doc -> Reset to PENDING? or DRAFT? Use DRAFT for safety.
        # 3. No Change -> Keep current
        
        current_status = current_doc.get("review_status", ReviewStatus.PENDING.value)
        new_status = current_status
        
        if is_content_changed:
            # 내용이 바뀌었으면 재검토 필요
            # 단, 최초 생성 시에는 PENDING이 기본일 수 있음.
            # 여기서는 운영 정책상 내용 변경 시 DRAFT로 내린다고 가정 (안전)
            # 하지만 최초 생성도 'changed' 취급이므로 구분 필요?
            if not current_doc:
                new_status = ReviewStatus.PENDING.value
            else:
                new_status = ReviewStatus.PENDING.value # or DRAFT
                # Prompt implies: "review_status: APPROVED | PENDING | REJECTED"
                # If content changes, it should go to PENDING for re-review.
                
        # 2. 서빙용 필드 구성
        
        # Card
        card_summary = card_data.get("card", {})
        # card_evidence = card_data.get("card_evidence", [])
        
        # Serving용 Card 구조 (프론트 규격에 맞게)
        serving_card = {
            "title": card_summary.get("l1", "No Title"),
            "summary": card_summary.get("l3", ""),
            "key_message": card_summary.get("l2", ""),
            # "evidence_refs": card_evidence
        }
        
        # Top Concepts
        top_concepts = current_doc.get("top_concepts", []) # Edge Ranker가 이미 넣었음
        
        # Metadata Merge
        final_doc = {
            # Key IDs
            "doc_id": doc_id,
            "tenant_id": Config.TENANT_ID,
            "engagement_id": Config.ENGAGEMENT_ID,
            
            # Base Meta (From Profile)
            "title": profile_data.get("title", "Untitled"),
            "folder_path": profile_data.get("folder_path", "/"),
            "doctype": profile_data.get("doctype_hint", "unknown"), # field name in profile is doctype_hint
            "modified_time": profile_data.get("modified_time"),
            "source_link": profile_data.get("source_link"),
            "doc_content_hash": profile_data.get("doc_content_hash"),
            "drive_file_id": profile_data.get("drive_file_id"), # Optional but good for link
            
            # Smart Meta
            "card_summary": { # Rename from card -> card_summary per requirements? 
                              # Req: card_summary: {l1, l2, l3}
                "l1": serving_card["title"],
                "l2": serving_card["key_message"],
                "l3": serving_card["summary"]
            },
            # "card": serving_card, # Keep legacy if needed? User req says "card_summary: {l1, l2, l3}"
            
            "security_level": SecurityLevel.normalize(policy_data.get("security_level")).value,
            "ssot_level": SSoTLevel.normalize(policy_data.get("ssot_level")).value,
            "matched_rules": policy_data.get("matched_rules", []),
            
            # Status
            "active": profile_data.get("active", True),
            "review_status": ReviewStatus.normalize(new_status).value,
            "index_version": Config.DOC_INDEX_VERSION,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        # Top Concepts는 이미 배열로 들어있다고 가정하고 유지
        if top_concepts:
            final_doc["top_concepts"] = top_concepts
        
        # 3. Upsert
        self.db.collection("documents").document(doc_id).set(final_doc, merge=True)
        
        # 4. Flag Off
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"index_meta": False}
        }, merge=True)
        
        logger.info(f"SUCCESS {doc_id}: Updated Index Meta.")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Doc Index Meta Upsert 작업 시작...")
        
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
    upserter = DocIndexUpserter()
    upserter.run_batch()
