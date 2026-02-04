from fastapi import APIRouter, Request, Query, HTTPException
from typing import Optional
from app.services.ai_a.allragpipeline.services.firestore_repo import FirestoreRepo
from app.services.ai_a.allragpipeline.services.graph_query_service import GraphQueryService

router = APIRouter(prefix="/api/graph", tags=["Graph"])

def get_service(request: Request) -> GraphQueryService:
    # Dependency Injection
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo = FirestoreRepo(auth_ctx)
    return GraphQueryService(repo)

from app.services.ai_a.allragpipeline.routers.mock_data import MOCK_GRAPH_GLOBAL, MOCK_GRAPH_EXPAND
import copy

@router.get("/init")
async def get_graph_init(
    request: Request,
    limit: Optional[int] = Query(None, description="Max nodes count")
):
    # [MOCK MODE] Static Global View (No RBAC)
    return MOCK_GRAPH_GLOBAL

@router.get("/expand")
async def expand_graph(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    limit: Optional[int] = Query(30, description="Max neighbors")
):
    # [MOCK MODE]
    # Dynamically link the new nodes to the requested node_id for visual consistency
    mock_data = copy.deepcopy(MOCK_GRAPH_EXPAND)
    for link in mock_data["links"]:
        link["source"] = node_id
    
    return mock_data

@router.get("/neighborhood")
async def get_neighborhood(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    limit: Optional[int] = Query(30)
):
    return await expand_graph(request, node_id, node_type, limit)
