from datetime import datetime # Added
from app.core.logger import log_system_event # Added

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.dependencies import get_current_user
from app.models.user import UserSchema
from app.services.drive_service import stream_file_to_gcs, list_files_in_folder_recursive
from app.services.docai_service import process_documents_batch
from app.services.ingestion_service import ingest_file_content, process_and_catalog_file
from app.services.log_service import log_user_action
from app.models.log import ActionType
from app.core.gcp_clients import db
from pydantic import BaseModel
from typing import List, Any, Dict

router = APIRouter(
    prefix="/drive",
    tags=["drive"],
    responses={404: {"description": "Not found"}},
)

# 요청 바디 모델 정의
class IngestRequest(BaseModel):
    file_id: str

class SyncFolderRequest(BaseModel):
    folder_id: str

class ProcessItem(BaseModel):
    file_id: str
    gcs_uri: str
    mime_type: str

class BatchProcessRequest(BaseModel):
    items: List[ProcessItem]

@router.post("/ingest")
async def ingest_drive_file(
    request: IngestRequest,
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Phase 2] 사용자의 구글 드라이브 파일을 GCS(Google Cloud Storage)로 스트리밍 전송합니다.
    [Refactoring] 공통 로직(process_and_catalog_file)을 사용하도록 변경됨.
    """
    if not current_user.google_access_token:
        raise HTTPException(status_code=400, detail="User is not connected to Google Drive")
        
    try:
        # Refactored Logic
        result = process_and_catalog_file(current_user, request.file_id)
        
        return {
            "status": "success",
            "message": "File streamed to GCS successfully",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def sync_folder_task(user: UserSchema, folder_id: str):
    """
    Background Task for Folder Sync
    """
    try:
        start_time = datetime.now()
        print(f"[Sync-Task] Starting background sync for {folder_id}")
        all_files = list_files_in_folder_recursive(user, folder_id)
        
        processed_count = 0
        failed_list = []
        
        # [System Status] Start Tracking
        db.collection("system_status").document(folder_id).set({
            "status": "running",
            "start_time": start_time,
            "total_files": len(all_files),
            "processed": 0
        })

        print(f"[Sync-Task] Found {len(all_files)} files. Starting ingestion...")
        
        for file_item in all_files:
            file_id = file_item['id']
            file_name = file_item['name']
            virtual_path = file_item.get('virtual_path')
            
            try:
                process_and_catalog_file(user, file_id, virtual_path=virtual_path)
                processed_count += 1
                
                # [Optional] Update progress periodically (e.g. every 5 files)
                if processed_count % 5 == 0:
                     db.collection("system_status").document(folder_id).update({"processed": processed_count})

            except Exception as e:
                print(f"[Sync-Task] Failed {file_name} ({file_id}): {e}")
                failed_list.append({
                    "file_id": file_id,
                    "name": file_name,
                    "error": str(e)
                })

        # Summary Log
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # [System Status] Complete Tracking
        db.collection("system_status").document(folder_id).update({
            "status": "completed",
            "end_time": end_time,
            "duration": duration,
            "processed": processed_count,
            "failed": len(failed_list)
        })
        
        # [Enrichment] Richer Context for AI-B
        
        # [Enrichment] Richer Context for AI-B
        details_payload = {
            "activity": "folder_sync_background",
            "folderId": folder_id,
            "totalFound": len(all_files),
            "processedCount": processed_count,
            "failedCount": len(failed_list),
            "durationSeconds": duration,
            "failedItems": failed_list[:10] # Top 10 failures only to save space
        }

        log_user_action(
            user=user,
            action=ActionType.VIEW,
            file_id=folder_id,
            success=True,
            details=details_payload
        )
        
        # [System Log] Also log to system stream for operational monitoring
        log_system_event(
            event_type="SYNC_COMPLETED",
            component="IngestRouter",
            payload=details_payload
        )
        print(f"[Sync-Task] Completed. Processed: {processed_count}/{len(all_files)}")

    except Exception as e:
        print(f"[Sync-Task] Critical Error: {e}")

@router.post("/sync-folder")
def sync_drive_folder(
    request: SyncFolderRequest,
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Feature] Recursive Folder Sync (Background)
    지정된 폴더의 동기화 작업을 백그라운드에서 실행하고, 즉시 응답을 반환합니다.
    (Timeout 방지)
    """
    if not current_user.google_access_token:
        raise HTTPException(status_code=400, detail="User is not connected to Google Drive")

    # Start Background Task
    background_tasks.add_task(sync_folder_task, current_user, request.folder_id)

    return {
        "status": "accepted",
        "message": "Folder sync started in background.",
        "folder_id": request.folder_id
    }

@router.post("/process/batch")
async def process_drive_files_batch(
    request: BatchProcessRequest,
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Phase 3 - Simplified] 다수의 GCS 파일에 대해 Document AI 배치를 실행하고,
    결과 JSON(docai_output.json)을 Firestore 'docai_results' 컬렉션에 저장합니다.
    (AI-A 팀으로의 Handoff Point)
    """
    # 1. Document AI Batch Processing
    # 이제 gcs_uris 리스트가 아니라, mime_type을 포함한 딕셔너리 리스트를 전달합니다.
    batch_items = [
        {"gcs_uri": item.gcs_uri, "mime_type": item.mime_type} 
        for item in request.items
    ]
    
    # DocAI 호출 (docai_output.json 매핑된 결과 반환)
    docai_results = process_documents_batch(batch_items)

    processed_count = 0
    artifacts_summary = []

    # Firestore 준비
    from app.core.gcp_clients import db
    collection_ref = db.collection('docai_results')

    for i, doc_output in enumerate(docai_results):
        original_item = request.items[i]
        
        # 에러 체크
        if "errors" in doc_output:
            artifacts_summary.append({
                "file_id": original_item.file_id, 
                "status": "failed", 
                "error": doc_output["errors"]
            })
            continue

        try:
            # 2. Firestore 저장 (Raw Output Transfer)
            # AI-A 팀이 가져갈 수 있도록 Raw JSON 저장
            # 문서 ID는 doc_id 사용
            doc_id = doc_output.get("doc_id", f"unknown_{original_item.file_id}")
            
            # 메타데이터 업데이트 (저장 시점, 요청자 등)
            # [Phase 3] Metadata Handoff Expansion
            file_meta_snapshot = db.collection('files').document(original_item.file_id).get()
            file_meta = file_meta_snapshot.to_dict() if file_meta_snapshot.exists else {}

            doc_output["_handoff_meta"] = {
                "saved_at": "timestamp", # 실제로는 datetime.now().isoformat()
                "requested_by": current_user.email,
                "user_department": current_user.department,
                "user_department_id": current_user.department_id,
                "file_created_at": str(file_meta.get("created_at", "")),
                "file_owner": file_meta.get("owners", [])
            }

            # source 영역에도 추가 정보 주입
            if "source" in doc_output:
                doc_output["source"]["drive_file_id"] = original_item.file_id
                doc_output["source"]["file_name"] = file_meta.get("name")
            
            # Upsert
            collection_ref.document(doc_id).set(doc_output)
            
            processed_count += 1
            artifacts_summary.append({
                "file_id": original_item.file_id,
                "doc_id": doc_id,
                "status": "success",
                "message": "Saved to Firestore 'docai_results'"
            })
            
        except Exception as e:
            print(f"Error saving to DB: {e}")
            artifacts_summary.append({
                "file_id": original_item.file_id,
                "status": "db_error",
                "error": str(e)
            })

    # [LogService] Process Batch Log
    # [LogService] Process Batch Log
    log_user_action(
        user=current_user,
        action=ActionType.VIEW,
        file_id="batch_process",
        success=True,
        details={
            "total": len(request.items),
            "processed": processed_count,
            "failed": len(request.items) - processed_count
        }
    )

    return {
        "status": "batch_completed",
        "processed_count": processed_count,
        "details": artifacts_summary
    }
