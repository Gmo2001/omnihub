from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.dependencies import get_current_user
from app.models.user import UserSchema
from app.services.drive_service import stream_file_to_gcs
from app.services.docai_service import process_documents_batch
from app.services.log_service import log_activity
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
    """
    if not current_user.google_access_token:
        raise HTTPException(status_code=400, detail="User is not connected to Google Drive")
        
    result = stream_file_to_gcs(current_user, request.file_id)
    
    # [LogService] Ingest Log
    log_activity(
        user=current_user,
        action="ingest_drive_file",
        resource=f"file:{request.file_id}",
        details={"gcs_uri": result.get("gcs_uri"), "size": result.get("size")}
    )
    
    return {
        "status": "success",
        "message": "File streamed to GCS successfully",
        "data": result
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
            doc_output["_handoff_meta"] = {
                "saved_at": "timestamp", # 실제로는 datetime.now().isoformat()
                "requested_by": current_user.email
            }
            
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
    log_activity(
        user=current_user,
        action="process_docai_batch",
        resource="batch",
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
