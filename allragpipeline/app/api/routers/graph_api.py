from fastapi import APIRouter, Request, Query, HTTPException
from typing import Optional
from app.services.firestore_repo import FirestoreRepo
from app.services.graph_query_service import GraphQueryService

router = APIRouter(prefix="/api/graph", tags=["Graph"])

def get_service(request: Request) -> GraphQueryService:
    # Dependency Injection
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo = FirestoreRepo(auth_ctx)
    return GraphQueryService(repo)

@router.get("/init")
async def get_graph_init(
    request: Request,
    limit: Optional[int] = Query(None, description="Max nodes count")
):
    try:
        service = get_service(request)
        result = service.get_overview(limit=limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expand")
async def expand_graph(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    limit: Optional[int] = Query(30, description="Max neighbors")
):
    try:
        if node_type not in ("document", "concept"):
            raise HTTPException(status_code=400, detail="Invalid node_type")
            
        service = get_service(request)
        result = service.expand_neighborhood(node_id=node_id, node_type=node_type, limit=limit)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/neighborhood")
async def get_neighborhood(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    limit: Optional[int] = Query(30)
):
    # Expand와 로직 동일 (프론트에서 용어 혼용 시 대비 alias)
    return await expand_graph(request, node_id, node_type, limit)
