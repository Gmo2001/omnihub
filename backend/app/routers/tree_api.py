import logging
import os
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from app.services.firestore_repo import FirestoreRepo

logger = logging.getLogger("TreeAPI")
router = APIRouter(prefix="/api/tree", tags=["Tree"])

DEFAULT_LIMIT = int(os.getenv("TREE_PAGE_SIZE_DEFAULT", 100))
MAX_LIMIT = int(os.getenv("TREE_PAGE_SIZE_MAX", 300))

import hashlib
from typing import Dict, Any

@router.get("")
async def get_tree_items(
    request: Request,
    folder: str = Query("/", description="Folder path to browse")
):
    """
    Lazy Loaded Tree: tree_index 컬렉션을 조회하여 폴더 및 파일 목록 반환
    """
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo = FirestoreRepo(auth_ctx)
    
    # 1. Path Normalization (Must match build_tree_index.py)
    normalized_path = folder.strip()
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    if not normalized_path.endswith("/"):
        normalized_path = normalized_path + "/"
        
    try:
        # 2. Key Generation
        path_hash = hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()[:16]
        tree_key = f"{auth_ctx.tenant_id}__{auth_ctx.engagement_id}__{path_hash}"
        
        # 3. Fetch from tree_index
        # Using repo.db directly for this optimized query
        doc_ref = repo.get_firestore_client().collection("tree_index").document(tree_key).get()
        
        if not doc_ref.exists:
            # If root path not found, return empty or check if it's first run
            if normalized_path == "/":
                return {"current_path": "/", "folders": [], "files": []}
            
            # If specific folder not found but path seems valid, return empty
            return {
                "current_path": normalized_path,
                "folders": [],
                "files": []
            }
            
        from app.services.permission_service import PermissionGuard
        
        data = doc_ref.to_dict()
        
        # 4. Filter by permissions (Enforce Security)
        raw_files = data.get("children_docs", [])
        
        # Inject Context scope for PermissionGuard (since it checks tenant/engagement equality)
        # Tree Index has them at root
        current_tenant = data.get("tenant_id")
        current_engagement = data.get("engagement_id")
        
        # Prepare for filtering
        # We need to inject these into each file dict because PermissionGuard checks doc['tenant_id']
        candidates = []
        for f in raw_files:
            # Shallow copy to avoid mutation if cached? (Firestore to_dict is fresh)
            f_enrich = f.copy()
            f_enrich["tenant_id"] = current_tenant
            f_enrich["engagement_id"] = current_engagement
            candidates.append(f_enrich)
            
        filtered_files = PermissionGuard.filter_docs(auth_ctx, candidates)
        
        return {
            "current_path": data.get("folder_path"),
            "folders": data.get("children_folders", []),
            "files": filtered_files
        }
        
    except Exception as e:
        logger.error(f"Tree Index Query Failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load tree structure")
