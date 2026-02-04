import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException
from app.services.ai_a.allragpipeline.services.firestore_repo import FirestoreRepo
from app.services.ai_a.allragpipeline.services.permission_guard import PermissionGuard

logger = logging.getLogger("CardDocsAPI")
router = APIRouter(prefix="/api/docs", tags=["Docs"])

# --- Helper (Dependency Injection) ---
def get_repo(request: Request) -> FirestoreRepo:
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return FirestoreRepo(auth_ctx)

from app.services.ai_a.allragpipeline.routers.mock_data import MOCK_DOC_CARD

@router.get("/{doc_id}")
async def get_doc_detail(request: Request, doc_id: str):
    # [MOCK MODE] Static Card (No RBAC)
    mock = MOCK_DOC_CARD.copy()
    mock["doc_id"] = doc_id
    return mock
