import logging
import os
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from app.services.ai_a.allragpipeline.services.firestore_repo import FirestoreRepo

logger = logging.getLogger("TreeAPI")
router = APIRouter(prefix="/api/tree", tags=["Tree"])

DEFAULT_LIMIT = int(os.getenv("TREE_PAGE_SIZE_DEFAULT", 100))
MAX_LIMIT = int(os.getenv("TREE_PAGE_SIZE_MAX", 300))

import hashlib
from typing import Dict, Any

from app.services.ai_a.allragpipeline.routers.mock_data import MOCK_TREE_GLOBAL

@router.get("")
async def get_tree_items(
    request: Request,
    folder: str = Query("/", description="Folder path to browse")
):
    # [MOCK MODE] Static Tree (No RBAC)
    return MOCK_TREE_GLOBAL
