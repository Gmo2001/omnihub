from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Query, Depends
from app.core.gcp_clients import db, get_drive_service
from app.services.log_service import log_user_action
from app.models.log import ActionType
from app.dependencies import get_current_user
from app.models.user import UserSchema
from typing import Optional

#파일과 관련된 모든 요청을 처리하는 곳

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
    try:
        doc_ref = db.collection('files').document(file_id)
        doc = doc_ref.get()
        
        if not doc.exists:  
            
            # [Phase 4] 실패 로그 (404 Not Found)
            log_user_action(
                user=current_user,
                action=ActionType.VIEW,
                file_id=file_id,
                success=False,
                details={"error": "File not found"}
            )
            raise HTTPException(status_code=404, detail="File not found")
        
        file_info = doc.to_dict()
        # [Removed] file_dept_id logic
        
        # 2. Log Integration (Real Context)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        
        # Background Task로 로그 저장
        background_tasks.add_task(
            log_user_action,
            user=current_user,
            action=ActionType.VIEW,
            file_id=file_id,
            success=True,
            ip_address=ip,
            details={"user_agent": ua}
        )
        
        return {"message": "File access success", "file": file_info}
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
            
        # [Phase 3] 예상치 못한 에러 로그
        # [Phase 4] 예상치 못한 에러 로그
        log_user_action(
            user=current_user,
            action=ActionType.VIEW,
            file_id=file_id,
            success=False,
            details={"error": str(e)}
        )
        raise e

@router.post("/files/{file_id}/download")
async def download_file(
    file_id: str, 
    request: Request, 
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):
    
    # [Log Integration] 다운로드 로그
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    
    # [Phase 3] 파일 정보 조회하여 부서 ID 확보 (DB 조회 Cost 추가됨)
    try:
        # doc = db.collection('files').document(file_id).get()  <-- DB 조회 불필요하면 제거 가능하지만, 파일 존재 체크용으로 둠
        
        background_tasks.add_task(
            log_user_action,
            user=current_user,
            action=ActionType.DOWNLOAD,
            file_id=file_id,
            success=True,
            ip_address=ip,
            details={"user_agent": ua}
        )
        
        return {"message": "Download started"}
        
    except Exception as e:
        log_user_action(
            user=current_user,
            action=ActionType.DOWNLOAD,
            file_id=file_id,
            success=False,
            details={"error": str(e)}
        )
        raise e