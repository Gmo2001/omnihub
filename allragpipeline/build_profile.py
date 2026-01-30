import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.PROJECT_ID: missing.append("GCP_PROJECT_ID")
        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("ProfileBuilder")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---

class ProfileBuilder:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        
    def get_doc_data(self, collection: str, doc_id: str) -> Dict[str, Any]:
        doc_ref = self.db.collection(collection).document(doc_id).get()
        if doc_ref.exists:
            return doc_ref.to_dict()
        return {}

    def process_document(self, base_doc_snapshot):
        doc_id = base_doc_snapshot.id
        base_data = base_doc_snapshot.to_dict()
        
        # 기본 필터링: active=True 인 것만 처리 (삭제된 파일 제외)
        if not base_data.get("active", True):
            logger.info(f"SKIP {doc_id}: Inactive (Deleted)")
            return

        logger.info(f"Building Profile for {doc_id}...")

        # 1. 원천 데이터 조회 (Multi-read)
        # base_data에 이미 sync_drive_to_gcs의 기본 정보가 있음
        file_meta = self.get_doc_data("file_metas", doc_id)
        drive_meta = self.get_doc_data("drive_metas", doc_id)
        docai_meta = self.get_doc_data("docai_artifacts", doc_id)
        
        # 2. 프로필 구성
        # 식별 정보
        tenant_id = Config.TENANT_ID
        engagement_id = Config.ENGAGEMENT_ID
        drive_file_id = base_data.get("drive_file_id")
        
        # GCS URIs 구조화
        gcs_uris = {
            "raw_file": file_meta.get("gcs_uri") or base_data.get("gcs_uri"),
            "docai_json": docai_meta.get("gcs_artifact_uri"),
            "normalized_text": docai_meta.get("normalized_text_uri"), # Optional if exists
            "tables_json": docai_meta.get("tables_json_uri") # Optional
        }
        
        # 변경 감지 해시
        doc_content_hash = file_meta.get("doc_content_hash")
        if not doc_content_hash:
            logger.warning(f"SKIP {doc_id}: Content Hash 미생성 (extract_file_meta 실행 필요)")
            return
            
        revision_id = drive_meta.get("version") or drive_meta.get("headRevisionId")

        # 타이틀 및 경로 (Metadata for downstream consumers, kept in profiles for reference)
        title = drive_meta.get("name") or base_data.get("filename") or "Untitled"
        folder_path = drive_meta.get("folder_path") or "/"
        source_link = drive_meta.get("source_link")
        
        # 힌트 정보
        doctype_hint = file_meta.get("doctype_hint", "unknown")
        owner_email = (drive_meta.get("owners") or [""])[0]
        perm_summary = drive_meta.get("permissions_summary", {})
        
        page_count = docai_meta.get("page_count", 0)

        # 3. 변경 감지 및 재처리 플래그 계산
        # 기존 프로필 조회
        old_profile_ref = self.db.collection("profiles").document(doc_id).get()
        old_hash = None
        if old_profile_ref.exists:
            old_hash = old_profile_ref.to_dict().get("doc_content_hash")
        
        needs_reprocess = False
        if old_hash != doc_content_hash:
            needs_reprocess = True
            logger.info(f" -> Change Detected ({old_hash} -> {doc_content_hash})")
        
        # Reprocess Flags (Hash 변경 시 전체 True)
        flags = {
            "policy": needs_reprocess,
            "chunk": needs_reprocess,
            "card": needs_reprocess,
            "entities": needs_reprocess,
            "concepts": needs_reprocess,
            "edges": needs_reprocess,
            "embed": needs_reprocess,
            "upsert": needs_reprocess,
            "index_meta": True # Always run meta update if profile changes
        }
        
        # 만약 기존 프로필이 없으면(신규) 당연히 True
        if not old_profile_ref.exists:
            flags = {k: True for k in flags}

        # 4. Profile 객체 생성 (Strict Schema)
        profile = {
            "doc_id": doc_id,
            "tenant_id": tenant_id,
            "engagement_id": engagement_id,
            
            # Key Pointers
            "gcs_uris": gcs_uris,
            "drive_file_id": drive_file_id,
            "doc_content_hash": doc_content_hash,
            "revision_id": revision_id,
            
            # Basic Meta (Source of Truth for builders)
            "title": title,
            "folder_path": folder_path,
            "source_link": source_link,
            "doctype_hint": doctype_hint,
            "owner_email": owner_email,
            "permissions_summary": perm_summary,
            "modified_time": file_meta.get("gcs_updated") or base_data.get("drive_modified_time"),
            "page_count": page_count,
            
            # System
            "process_flags": flags,
            "profile_updated_at": firestore.SERVER_TIMESTAMP,
            "active": True
        }

        # 5. 저장 (Profiles ONLY)
        batch = self.db.batch()
        
        # profiles/{doc_id}
        profile_ref = self.db.collection("profiles").document(doc_id)
        batch.set(profile_ref, profile, merge=True)
        
        # documents 컬렉션 쓰기 제거됨. (Responsibility: upsert_doc_index_meta.py)
        
        batch.commit()
        logger.info(f"SUCCESS {doc_id}: Profile Updated.")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Profile Build 작업 시작...")
        
        # documents 컬렉션 순회 (active=True)
        # 혹은 file_metas에서 출발해도 됨. documents가 SSOT.
        docs = self.db.collection("documents").where(filter=firestore.FieldFilter("active", "==", True)).stream()
        
        count = 0
        for doc in docs:
            try:
                self.process_document(doc)
                count += 1
            except Exception as e:
                logger.error(f"Error processing {doc.id}: {e}")
        
        logger.info(f"작업 완료. 총 {count}개 프로필 생성/갱신.")

if __name__ == "__main__":
    builder = ProfileBuilder()
    builder.run_batch()
