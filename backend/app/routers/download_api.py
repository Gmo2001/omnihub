import logging
import os
import datetime
from fastapi import APIRouter, Request, HTTPException
from google.cloud import storage
from app.services.firestore_repo import FirestoreRepo

from app.services.signed_url_service import SignedURLService
from app.services.permission_service import PermissionGuard

logger = logging.getLogger("DownloadAPI")
router = APIRouter(prefix="/api/docs", tags=["Download"])
signer = SignedURLService()

@router.get("/{doc_id}/download")
async def download_document(request: Request, doc_id: str):
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    repo = FirestoreRepo(auth_ctx)
    
    # 1. 문서 조회 (Repo Scope Check 포함)
    doc = repo.get_document(doc_id)
    if not doc:
         raise HTTPException(status_code=404, detail="Document Not Found")

    # 2. 다운로드 권한/정책 검사 (PermissionGuard)
    # - Tenant/Engagement 격리 (repo.get_document에서 이미 됨)
    # - Review Status & Security Level 검사
    PermissionGuard.ensure_download_allowed(auth_ctx, doc)
    
    # 3. GCS URI 확인
    gcs_uri = doc.get("gcs_uri")
    if not gcs_uri:
        # DB에 gcs_uri가 없으면 원본이 없는 것. 
        raise HTTPException(status_code=404, detail="Source file not found")
        
    # 4. Signed URL 발급
    try:
        # 파일명 오버라이드 (Optional: doc title 사용)
        filename = doc.get("title")
        if filename and not filename.endswith(".pdf"): # 확장자 보정 (간단 예시)
            filename += ".pdf"
            
        url = signer.generate_download_link(gcs_uri, filename=filename)
        
        return {
            "doc_id": doc_id,
            "url": url,
            "expires_in_seconds": 300 # Default from service
        }
    except Exception as e:
        logger.error(f"Sign URL Failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download link")
