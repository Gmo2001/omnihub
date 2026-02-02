from datetime import datetime # Added
from app.core.logger import log_system_event # Added

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from google.cloud import firestore # Added for ArrayUnion
from app.dependencies import get_current_user
from app.models.user import UserSchema
from app.services.drive_service import stream_file_to_gcs, list_files_in_folder_recursive
from app.services.rag.steps.run_docai_extract import DocAIExtractor # [Modified] Use new Extractor from run_docai_extract
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

    # [RAG Pipeline Trigger]
    try:
        from app.services.rag.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator()
        
        # internal_id extraction (fil_ prefix)
        internal_file_id = result.get("file_id") 
        gcs_uri = result.get("gcs_uri")
        mime_type = result.get("mime_type")

        # Run in background to execute full pipeline
        background_tasks.add_task(
            orchestrator.run_pipeline, 
            file_id=internal_file_id,
            gcs_uri=gcs_uri,
            mime_type=mime_type
        )
        print(f"🚀 [Ingest] RAG Pipeline triggered for {internal_file_id}")
        
    except Exception as e:
        print(f"⚠️ [Ingest] Failed to trigger RAG Pipeline: {e}")

    return {
        "status": "success",
        "message": "File streamed and RAG Pipeline started",
        "data": result
    }

import asyncio

async def sync_folder_task(user: UserSchema, folder_id: str):
    """
    Background Task for Folder Sync
    [Optimized] Uses Asyncio Benchmark & Delta Sync
    """
    try:
        start_time = datetime.now()
        print(f"[Sync-Task] Starting background sync for {folder_id}")
        
        # 1. List Files (Sync execution in thread to avoid blocking)
        all_files = await asyncio.to_thread(list_files_in_folder_recursive, user, folder_id)
        
        processed_count = 0
        skipped_count = 0 # Track skipped files
        failed_list = []
        
        # [System Status] Start Tracking
        db.collection("system_status").document(folder_id).set({
            "status": "running",
            "start_time": start_time,
            "total_files": len(all_files),
            "processed": 0,
            "skipped": 0
        })

        print(f"[Sync-Task] Found {len(all_files)} files. Starting Batch Ingestion (Concurrency: 5)...")
        
        # 2. Batch Processing Setup
        semaphore = asyncio.Semaphore(5) # Limit concurrency to avoid OOM or Rate Limits

        async def process_wrapper(file_item):
            async with semaphore:
                try:
                    # Run sync blocking IO in thread pool
                    result = await asyncio.to_thread(
                        process_and_catalog_file, 
                        user, 
                        file_item['id'], 
                        virtual_path=file_item.get('virtual_path'),
                        drive_meta=file_item # Pass meta for Delta Check
                    )
                    return {"status": "success", "file_item": file_item, "result": result}
                except Exception as e:
                    return {"status": "error", "file_item": file_item, "error": str(e)}

        # 3. Execute concurrently
        tasks = [process_wrapper(item) for item in all_files]
        
        # 4. Monitor Progress
        for i, future in enumerate(asyncio.as_completed(tasks)):
            res = await future
            processed_count += 1
            
            if res["status"] == "success":
                # Check if skipped
                if res["result"].get("status") == "skipped":
                    skipped_count += 1
            else:
                f_item = res["file_item"]
                print(f"[Sync-Task] Failed {f_item['name']} ({f_item['id']}): {res['error']}")
                failed_list.append({
                    "file_id": f_item['id'],
                    "name": f_item['name'],
                    "error": res['error']
                })
            
            # Periodic Update (Every 5 files)
            if processed_count % 5 == 0:
                db.collection("system_status").document(folder_id).update({
                    "processed": processed_count,
                    "skipped": skipped_count
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
            "skipped": skipped_count,
            "failed": len(failed_list)
        })
        
        # [Enrichment] Richer Context
        details_payload = {
            "activity": "folder_sync_background",
            "folderId": folder_id,
            "totalFound": len(all_files),
            "processedCount": processed_count,
            "skippedCount": skipped_count, # Added
            "failedCount": len(failed_list),
            "durationSeconds": duration,
            "failedItems": failed_list[:10] 
        }

        log_user_action(
            user=user,
            action=ActionType.VIEW,
            file_id=folder_id,
            success=True,
            details=details_payload
        )
        
        # [System Log]
        log_system_event(
            event_type="SYNC_COMPLETED",
            component="IngestRouter",
            payload=details_payload
        )
        print(f"[Sync-Task] Completed. Total: {len(all_files)}, Skipped: {skipped_count}, Failed: {len(failed_list)}")

    except Exception as e:
        print(f"[Sync-Task] Critical Error: {e}")
        # Mark as failed in DB
        db.collection("system_status").document(folder_id).set({
             "status": "failed",
             "error": str(e),
             "end_time": datetime.now()
        }, merge=True)

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

    # [Privacy Guard] Auto-whitelist this folder
    try:
        user_ref = db.collection('users').document(current_user.email)
        # Use ArrayUnion to append without reading first (Atomic)
        user_ref.update({
            "monitored_folder_ids": firestore.ArrayUnion([request.folder_id])
        })
        print(f"[Privacy] Whitelisted folder {request.folder_id} for {current_user.email}")
    except Exception as e:
        print(f"[Privacy] Failed to whitelist folder: {e}")

    return {
        "status": "accepted",
        "message": "Folder sync started in background.",
        "folder_id": request.folder_id
    }

@router.post("/process/batch")
async def process_drive_files_batch(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks, # 백그라운드 필수
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Phase 3] DocAI 비동기 처리 요청
    """
    extractor = DocAIExtractor()
    queued_count = 0
    
    for item in request.items:
        # BackgroundTasks에 작업 등록 (서버 블로킹 방지)
        background_tasks.add_task(
            extractor.process_single_document,
            file_id=item.file_id,
            gcs_uri=item.gcs_uri,
            mime_type=item.mime_type
        )
        queued_count += 1
        
        # 상태 업데이트
        db.collection('files').document(item.file_id).update({
            "aiStatus": "processing",
            "aiMethod": "docai_batch_async"
        })

    return {
        "status": "batch_queued",
        "queued_count": queued_count,
        "message": f"{queued_count}건의 문서가 백그라운드 처리 대기열에 등록되었습니다."
    }
