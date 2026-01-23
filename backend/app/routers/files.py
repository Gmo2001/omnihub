from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Query
from app.core.gcp_clients import db, get_drive_service
from app.models.log import ActionType
from app.services.log_service import LogService
from app.services.log_service import LogService
from typing import Optional
from fastapi import Depends
from app.dependencies import get_current_user
from app.models.user import UserSchema


#파일과 관련된 모든 요청을 처리하는 곳

router = APIRouter()
log_service = LogService()

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
    (Real DB Use)
    """
    try:
        docs = db.collection('files').stream()
        
        tree = {"name": "Root", "children": [], "is_folder": True}
        
        for doc in docs:
            data = doc.to_dict()
            v_path = data.get('virtual_path') 
            
            if not v_path:
                continue
                
            # 트리 구조 만들기 로직 (간소화)
            current_node = tree
            parts = v_path.strip("/").split("/")
            
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
            
            # 리프 노드에 파일 추가
            file_node = {
                "name": data.get('name'),
                "id": data.get('file_id'),
                "mime_type": data.get('mime_type'),
                "is_folder": False
            }
            current_node["children"].append(file_node)
            
        return tree
        
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

# 3. File Detail & Logging (Real DB)
@router.get("/files/{file_id}")
async def get_file(
    file_id: str, 
    request: Request, 
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):

    """
    파일 상세 정보를 조회하고, 접근 로그를 남깁니다.
    """
    # 1. Real DB Query
    doc_ref = db.collection('files').document(file_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_info = doc.to_dict()
    
    # 2. Log Integration (Real Context)
    # JWT/Session에서 user_id를 추출
    current_user_id = current_user.uid
 
    
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    
    # Background Task로 로그 저장
    background_tasks.add_task(
        log_service.create_log,
        user_id=current_user_id,
        file_id=file_id,
        action=ActionType.VIEW,
        success=True,
        ip_address=ip,
        user_agent=ua
    )
    
    return {"message": "File access success", "file": file_info}

@router.post("/files/{file_id}/download")
@router.post("/files/{file_id}/download")
async def download_file(
    file_id: str, 
    request: Request, 
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):
    current_user_id = current_user.uid

    
    # [Log Integration] 다운로드 로그
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    
    background_tasks.add_task(
        log_service.create_log,
        user_id=current_user_id,
        file_id=file_id,
        action=ActionType.DOWNLOAD,
        success=True,
        ip_address=ip,
        user_agent=ua
    )
    
    return {"message": "Download started"}