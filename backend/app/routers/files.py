from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Query, Depends
from app.core.gcp_clients import db, get_drive_service
from app.services.log_service import log_activity
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
            # [Phase 3] 실패 로그 (404 Not Found)
            log_activity(
                user=current_user, 
                action="view_file", 
                resource=f"file:{file_id}", 
                details={"success": False, "error": "File not found"}
            )
            raise HTTPException(status_code=404, detail="File not found")
        
        file_info = doc.to_dict()
        file_dept_id = file_info.get("department_id") # [Phase 3]
        
        # 2. Log Integration (Real Context)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        
        # Background Task로 로그 저장
        background_tasks.add_task(
            log_activity,
            user=current_user,
            action="view_file",
            resource=f"file:{file_id}",
            details={
                "success": True,
                "ip_address": ip,
                "user_agent": ua,
                "file_department_id": file_dept_id # [Phase 3] AI-B Check
            }
        )
        
        return {"message": "File access success", "file": file_info}
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
            
        # [Phase 3] 예상치 못한 에러 로그
        log_activity(
            user=current_user,
            action="view_file",
            resource=f"file:{file_id}",
            details={"success": False, "error": str(e)}
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
        doc = db.collection('files').document(file_id).get()
        file_dept_id = doc.to_dict().get("department_id") if doc.exists else None
        
        background_tasks.add_task(
            log_activity,
            user=current_user,
            action="download_file",
            resource=f"file:{file_id}",
            details={
                "success": True,
                "ip_address": ip,
                "user_agent": ua,
                "file_department_id": file_dept_id # [Phase 3]
            }
        )
        
        return {"message": "Download started"}
        
    except Exception as e:
        log_activity(
            user=current_user,
            action="download_file",
            resource=f"file:{file_id}",
            details={"success": False, "error": str(e)}
        )
        raise e