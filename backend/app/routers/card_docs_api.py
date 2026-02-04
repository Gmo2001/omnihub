import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException
from app.services.firestore_repo import FirestoreRepo
from app.services.permission_service import PermissionGuard

logger = logging.getLogger("CardDocsAPI")
router = APIRouter(prefix="/api/docs", tags=["Docs"])

# --- Helper (Dependency Injection) ---
def get_repo(request: Request) -> FirestoreRepo:
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return FirestoreRepo(auth_ctx)

@router.get("/{doc_id}")
async def get_doc_detail(request: Request, doc_id: str):
    repo = get_repo(request)
    
    # 1. 문서 메타 조회
    doc = repo.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document Not Found")
        
    # 2. 권한 체크 (PermissionGuard 강제 적용)
    # auth_ctx is guaranteed by get_repo
    auth_ctx = request.state.auth_ctx
    PermissionGuard.ensure_doc_access(auth_ctx, doc)

    # 3. 추가 정보 조회 (Card, Evidence)
    # documents 컬렉션에 card_summary ({l1, l2, l3})가 있음.
    
    card_summary = doc.get("card_summary", {})
    # Fallback for legacy
    if not card_summary and "card" in doc:
        # Legacy mapping if strictly needed (Operating Minimum: keep logic simple)
        pass

    embedding_evidence = []
    # Fetch detailed card from 'cards' collection to get evidence
    detailed_card = repo.get_card(doc_id)
    if detailed_card:
        embedding_evidence = detailed_card.get("card_evidence", [])

    return {
        "doc_id": doc_id,
        "title": doc.get("title"),
        "folder_path": doc.get("folder_path"),
        "modified_time": doc.get("modified_time"),
        "source_link": doc.get("source_link"),
        "review_status": doc.get("review_status"),
        
        # UI likely expects 'card' with l1, l2, l3
        "card": card_summary, 
        
        "policy": {
            "security_level": doc.get("security_level"),
            "ssot_level": doc.get("ssot_level")
        },
        
        "concepts": doc.get("top_concepts", []),
        
        # evidence: Card 요약의 근거 (페이지 번호 등)
        "evidence": embedding_evidence 
    }
