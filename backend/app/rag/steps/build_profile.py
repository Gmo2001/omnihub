import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from google.cloud import firestore

# [통합] 기존 프로젝트 Config 사용
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# 로거 설정
logger = logging.getLogger("ProfileBuilder")
logger.setLevel(logging.INFO)

# --- Core Logic ---

class ProfileBuilder:
    def __init__(self):
        # [통합] 전역 DB 클라이언트 사용
        self.db = get_firestore_client()
        self.tenant_id = getattr(settings, "TENANT_ID", "default_tenant")
        self.engagement_id = getattr(settings, "ENGAGEMENT_ID", "default_engagement")
        
    def get_doc_data(self, collection: str, doc_id: str) -> Dict[str, Any]:
        """Firestore 문서 조회 헬퍼"""
        doc_ref = self.db.collection(collection).document(doc_id).get()
        if doc_ref.exists:
            return doc_ref.to_dict()
        return {}

    def process_single_document(self, file_id: str):
        """
        단일 문서에 대해 Profile Build를 수행합니다.
        - Ingestion -> DocAI 처리 후 호출되는 단계입니다.
        - 여러 소스(file_metas, docai_artifacts 등)를 조회하여 profiles 컬렉션을 생성합니다.
        """
        doc_id = file_id # 여기서는 file_id를 doc_id로 사용

        logger.info(f"🏗️ [Profile] 빌드 시작: {doc_id}")

        # 0. 기본 데이터 확인 (files 컬렉션 = documents 역할)
        base_doc_ref = self.db.collection("files").document(doc_id).get()
        if not base_doc_ref.exists:
            logger.warning(f"SKIP {doc_id}: 기본 파일 정보 없음")
            return
        base_data = base_doc_ref.to_dict()

        # 1. 원천 데이터 조회 (Multi-read)
        # [통합] 기존 Ingest 로직에서 생성된 데이터 매핑
        # - file_metas -> files (이미 base_data에 포함됨)
        # - docai_artifacts -> docai_results
        
        docai_data = self.get_doc_data("docai_results", doc_id)
        
        # 2. 프로필 구성
        # 식별 정보
        drive_file_id = base_data.get("fileId", doc_id) # 'fileId' or fallback
        
        # GCS URIs 구조화
        gcs_uris = {
            "raw_file": base_data.get("gcsUri"),
            "docai_json": docai_data.get("raw_output_uri"), # docai_results의 필드명 확인 필요
            "full_text": None # Full text is in Firestore body, not GCS uri usually in this flow? Ah, wait.
            # docai_results에 full_text가 저장되어 있음. GCS URI가 필요하면 docai output 경로 사용.
        }
        
        # 해시 생성 (없으면 임시 생성)
        # [통합] Ingest 단계에서 해시를 아직 안 만들었을 수 있음.
        # Modified Time을 해시 대용으로 사용하거나, 추후 추가 필요.
        doc_content_hash = base_data.get("doc_content_hash")
        if not doc_content_hash:
            # Fallback: Use modified time + size
            mod_time = str(base_data.get("driveModifiedTime", ""))
            size = str(base_data.get("size", ""))
            doc_content_hash = f"hash_{mod_time}_{size}"

        revision_id = base_data.get("version", "1")

        # 타이틀 및 경로
        title = base_data.get("name", "Untitled")
        folder_path = base_data.get("fullPath", "/")
        source_link = base_data.get("webViewLink", "")
        
        # 힌트 정보
        doctype_hint = base_data.get("mimeType", "application/octet-stream")
        owner_email = (base_data.get("owners") or [""])[0]
        
        page_count = base_data.get("pageCount", 0)

        # 3. 변경 감지 및 재처리 플래그 계산
        old_profile_ref = self.db.collection("profiles").document(doc_id).get()
        old_hash = None
        if old_profile_ref.exists:
            old_hash = old_profile_ref.to_dict().get("doc_content_hash")
        
        needs_reprocess = False
        if old_hash != doc_content_hash:
            needs_reprocess = True
            logger.info(f" -> 변경 감지됨 ({old_hash} -> {doc_content_hash})")
        
        # Reprocess Flags
        # 신규 파일이거나 변경되었으면 True
        is_new = not old_profile_ref.exists
        should_run = is_new or needs_reprocess

        flags = {
            "policy": should_run,
            "chunk": should_run,
            "card": should_run,
            "entities": should_run,
            "concepts": should_run,
            "edges": should_run,
            "embed": should_run,
            "upsert": should_run,
            "index_meta": True 
        }

        # 4. Profile 객체 생성
        profile = {
            "doc_id": doc_id,
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            
            # Key Pointers
            "gcs_uris": gcs_uris,
            "drive_file_id": drive_file_id,
            "doc_content_hash": doc_content_hash,
            "revision_id": revision_id,
            
            # Basic Meta
            "title": title,
            "folder_path": folder_path,
            "source_link": source_link,
            "doctype_hint": doctype_hint,
            "owner_email": owner_email,
            "permissions_summary": {}, # TODO: Fetch perms if needed
            "modified_time": base_data.get("driveModifiedTime"),
            "page_count": page_count,
            
            # System
            "process_flags": flags,
            "profile_updated_at": firestore.SERVER_TIMESTAMP,
            "active": True
        }

        # 5. 저장 (Profiles)
        self.db.collection("profiles").document(doc_id).set(profile, merge=True)
        
        # 6. [Safety] Documents 컬렉션에도 Title 백업 (검색 엔진 Fallback용)
        self.db.collection("documents").document(doc_id).set({"title": title}, merge=True)
        
        logger.info(f"✅ [Profile] 생성 및 백업 완료: {doc_id}")
        
        # [Extension Point] 다음 단계 호출 가능
        # if flags['policy']:
        #     classify_doc_policy.process(doc_id)

    def run_batch(self):
        """배치 실행 (전체 재조정용)"""
        logger.info("Batch Profile Build 시작...")
        docs = self.db.collection("files").where("status", "==", "synced").stream()
        
        count = 0
        for doc in docs:
            # docai_results가 있는 파일만 처리
            if self.db.collection("docai_results").document(doc.id).get().exists:
                self.process_single_document(doc.id)
                count += 1
        
        logger.info(f"Batch 완료. 총 {count}개 프로필 갱신.")

