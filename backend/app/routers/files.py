from fastapi import APIRouter, HTTPException, Query
from app.core.gcp_clients import get_drive_service, db
from app.models.file import FileSchema
from typing import List, Dict, Any, Optional
from app.services.sync_service import sync_file_metadata

router = APIRouter()

# 1. Real Drive Proxy API
@router.get("/files/drive/proxy")
async def get_drive_files_proxy(folder_id: str = Query("root")):
    """
    실제 구글 드라이브의 파일 목록을 실시간으로 중계합니다. (탐색기용)
    """
    service = get_drive_service()
    try:
        # folder_id 안의 파일들만 조회 (trashed 된거 제외)
        query = f"'{folder_id}' in parents and trashed = false"
        
        # 필요한 필드만 콕 집어서 가져옴 (속도 최적화)
        fields = "files(id, name, mimeType, iconLink, webViewLink, hasThumbnail, thumbnailLink)"
        
        results = service.files().list(
            q=query,
            pageSize=100,
            fields=fields,
            orderBy="folder, name"
        ).execute()
        
        return {"files": results.get('files', [])}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Virtual Tree API
@router.get("/files/virtual-tree")
async def get_virtual_tree():
    """
    AI가 분류한 '가상 폴더 구조'를 트리 형태로 반환합니다.
    Firestore에서 virtual_path 필드를 사용하여 계층 구조를 조립합니다.
    """
    try:
        # 모든 파일 가져오면 너무 많을 수 있으니, virtual_path가 있는 것만 조회 (인덱스 필요할 수 있음)
        # 프로토타입 단계에서는 전체 조회 후 메모리 필터링이 편할 수 있음
        docs = db.collection('files').stream()
        
        tree = {"name": "Root", "children": [], "is_folder": True}
        
        for doc in docs:
            data = doc.to_dict()
            v_path = data.get('virtual_path') # 예: "/인사팀/2026/채용"
            
            if not v_path:
                continue
                
            # 트리 구조 만들기 로직
            current_node = tree
            parts = v_path.strip("/").split("/")
            
            # 경로 따라가며 노드 생성
            for part in parts:
                found = False
                for child in current_node["children"]:
                    if child["name"] == part and child.get("is_folder"):
                        current_node = child
                        found = True
                        break
                
                if not found:
                    new_node = {"name": part, "children": [], "is_folder": True}
                    current_node["children"].append(new_node)
                    current_node = new_node
            
            # 마지막 리프 노드에 파일 추가
            file_node = {
                "name": data.get('name'),
                "id": data.get('file_id'),
                "mime_type": data.get('mime_type'),
                "is_folder": False,
                # 필요하면 더 많은 필드 추가
            }
            current_node["children"].append(file_node)
            
        return tree
        
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

# 3. Dashboard Stats API
@router.get("/dashboard/stats")
async def get_dashboard_stats():
    """
    대시보드 차트용 통계 데이터를 집계하여 반환합니다.
    """
    try:
        files_ref = db.collection('files')
        
        # 3.1 전체 파일 수 (카운트 쿼리)
        # aggregate_query = files_ref.count() # 최신 firebase-admin SDK 필요
        # 간단하게 stream() len으로 (프로토타입용, 나중에 count()로 최적화)
        docs = list(files_ref.stream()) 
        total_count = len(docs)
        
        # 3.2 상태별 카운트
        pending_count = sum(1 for d in docs if d.to_dict().get('status') == 'pending')
        processed_count = sum(1 for d in docs if d.to_dict().get('status') == 'processed')
        
        # 3.3 최근 활동 (Recent 5)
        # (원래는 order_by('created_at', 'DESC').limit(5) 써야 함)
        sorted_docs = sorted(docs, key=lambda x: x.to_dict().get('created_at', ''), reverse=True)[:5]
        recent_activity = []
        for d in sorted_docs:
            data = d.to_dict()
            recent_activity.append({
                "name": data.get('name'),
                "status": data.get('status'),
                "time": data.get('created_at')
            })
            
        return {
            "total_files": total_count,
            "status_summary": {
                "pending": pending_count,
                "processed": processed_count
            },
            "recent_activity": recent_activity
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))