import logging
from typing import Optional
from enum import Enum
from pydantic import BaseModel

from fastapi import APIRouter, Request, HTTPException
from app.services.firestore_repo import FirestoreRepo
from app.common.enums import ReviewStatus

logger = logging.getLogger("DocsStatusAPI")
router = APIRouter(prefix="/api/docs", tags=["DocsStatus"])

# Use ReviewStatus directly or alias if needed by specific framework logic, 
# but Pydantic works with Enum.
DocStatus = ReviewStatus

class UpdateStatusRequest(BaseModel):
    status: DocStatus
    reason: Optional[str] = None

from app.rag.doc_workflow_rules import DocWorkflowRules

@router.patch("/{doc_id}/status")
async def update_doc_status(request: Request, doc_id: str, body: UpdateStatusRequest):
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # 1. Role Check
    roles = getattr(auth_ctx, "roles", [])
    if "admin" not in roles and "reviewer" not in roles:
        raise HTTPException(status_code=403, detail="Permission Denied: Reviewer or Admin role required")
    
    repo = FirestoreRepo(auth_ctx)
    
    # 2. Scope & Permission Check (Implicit in repo usage, but we do get_document first)
    # repo.update_doc_status does check existence internally, but getting doc first is safer for logic
    doc = repo.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document Not Found or Access Denied")
        
    # 3. Calculate Updates via Workflow Rules
    updates = DocWorkflowRules.apply(body.status.value)
    
    # 4. Update Status & Active Flags using extended repo method
    try:
        repo.update_doc_status(doc_id, body.status.value, body.reason, updates=updates)

        return {
            "doc_id": doc_id,
            "status": body.status.value,
            "updates_applied": updates,
            "updated_by": auth_ctx.user_id
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Status Update Failed: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

