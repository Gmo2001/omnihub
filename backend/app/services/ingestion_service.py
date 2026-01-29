from app.core.gcp_clients import get_drive_service, db
import io
from googleapiclient.http import MediaIoBaseDownload
from app.models.user import UserSchema
from datetime import datetime
from google.cloud import firestore
from app.services.drive_service import stream_file_to_gcs, resolve_full_path # Added import
from app.services.bq_service import stream_files_to_bigquery # Added BQ Service
from app.core.gcp_clients import get_drive_service, db # Restore db
from googleapiclient.http import MediaIoBaseDownload # Restore class
from app.utils.id_utils import to_internal_id # Restore util
from app.services.log_service import log_user_action # Restore log
from app.models.log import ActionType # Restore enum
import io 

def ingest_file_content(file_id: str, mime_type: str, drive_service=None) -> str:
    """
    Google Drive 파일의 내용을 텍스트로 추출합니다.
    - Google Docs/Sheets/Slides: text/plain으로 변환(Export)하여 다운로드
    - 일반 텍스트/PDF: 바이너리 다운로드 (현재는 텍스트 파일 단순 디코딩 예시)
    """
    service = drive_service if drive_service else get_drive_service()
    content = ""
    
    try:
        # 1. Google Workspace 문서 (Docs, Sheets, Slides) -> Text Export
        if mime_type.startswith("application/vnd.google-apps"):
            if "folder" in mime_type:
                return "" # 폴더는 내용 없음
            
            # export() 사용: 구글 전용 포맷을 일반 텍스트로 변환
            # Sheets는 csv, Slides는 plain text 등으로 변환됨
            response = service.files().export(
                fileId=file_id, 
                mimeType='text/plain'
            ).execute()
            
            # export 결과는 bytes 형태이므로 디코딩
            content = response.decode('utf-8')
            print(f"[Ingestion] Exported Google Doc {file_id} (len: {len(content)})")
            
        # 2. 일반 파일 (txt, md, csv 등) -> Binary Download
        # PDF의 경우 별도의 OCR/PDF 파서(PyPDF2, PDFPlumber 등)가 필요하므로
        # 여기서는 단순 텍스트 기반 파일만 처리한다고 가정합니다.
        else:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # 다운로드 완료 후 포인터 리셋
            fh.seek(0)
            
            # 텍스트 파일로 가정하고 디코딩 시도 (바이너리 파일은 에러날 수 있음)
            try:
                content = fh.read().decode('utf-8')
                print(f"[Ingestion] Downloaded File {file_id} (len: {len(content)})")
            except UnicodeDecodeError:
                content = f"[Binary Content] Mime-Type: {mime_type} (Non-text file)"
                print(f"[Ingestion] Binary file detected: {file_id}")

        return content

    except Exception as e:
        print(f"Error extracting content for {file_id}: {str(e)}")
        # 에러 발생 시 None 대신 빈 문자열 반환하거나 에러를 상위로 전파
        return ""

def process_and_catalog_file(user: UserSchema, file_id: str, virtual_path: str = None) -> dict:
    """
    단일 파일을 GCS로 스트리밍하고, Firestore에 메타데이터(부서 정보, 가상 경로 등)를 등록합니다.
    (기존 ingest.py의 로직을 캡슐화)
    """
    # [Standardization] Ensure ID has prefix (fil_XXX)
    file_id = to_internal_id('fil_', file_id)

    # 1. Stream to GCS
    try:
        result = stream_file_to_gcs(user, file_id)
    except Exception as e:
        print(f"[Ingest] Streaming failed for {file_id}: {e}")
        raise e

    # 2. Stamp Metadata in Firestore (CamelCase Compliance)
    try:
        # Resolve Full Path (If not provided by recursive sync)
        if virtual_path:
            full_path = virtual_path
        else:
            full_path = resolve_full_path(user, file_id)

        # Prepare Metadata (CamelCase for BigQuery/Firestore consistency)
        meta = result.get("metadata", {})
        
        # Date parsing (ISO to Datetime)
        created_at_dt = None
        if "createdTime" in meta:
            try:
                created_at_dt = datetime.fromisoformat(meta["createdTime"].replace("Z", "+00:00"))
            except: pass

        update_data = {
            "fileId": file_id,
            "fileDeptId": user.department_id, # departmentId -> fileDeptId Rename for Spec Match
            
            # [Fix] Common Rules: CamelCase Keys
            "name": meta.get("name", result.get("file_name")),
            "mimeType": result.get("mime_type"),
            
            "fullPath": full_path, # virtual_path -> fullPath rename
            
            "gcsUri": result.get("gcs_uri"),
            
            # Additional Drive Meta
            "owners": [owner.get("displayName") for owner in meta.get("owners", [])],
            "lastModifiedBy": meta.get("lastModifyingUser", {}).get("displayName", "Unknown"),
            "webViewLink": meta.get("webViewLink"),
            "iconLink": meta.get("iconLink"),
            
            # Timestamps
            "createdAt": created_at_dt,
            "updatedAt": firestore.SERVER_TIMESTAMP, # [Fix] Use Server Timestamp, not string
            
            # Status Flags
            "status": "synced",
            "aiStatus": "pending",
            
            "isFolder": False,
            "trashed": meta.get("trashed", False)
        }

        db.collection('files').document(file_id).set(update_data, merge=True)
        print(f"[Ingest] Stamped metadata for {file_id} (Path: {full_path})")
        
        # 3. Stream to BigQuery (Direct Insert)
        # [Fix] Handle Firestore Sentinel for JSON serialization
        bq_data = update_data.copy()
        if bq_data.get("updatedAt") == firestore.SERVER_TIMESTAMP:
            bq_data["updatedAt"] = datetime.utcnow().isoformat()
        if isinstance(bq_data.get("createdAt"), datetime):
            bq_data["createdAt"] = bq_data["createdAt"].isoformat()
            
        stream_files_to_bigquery(bq_data, file_id)
        
    except Exception as e:
        print(f"[Warning] Failed to stamp metadata on file {file_id}: {e}")

    # 3. Log Action
    log_user_action(
        user=user,
        action=ActionType.DOWNLOAD, # Ingest를 Download로 정의함 (Drive -> GCS)
        file_id=file_id,
        success=True,
        details={
            "gcsUri": result.get("gcs_uri"), 
            "size": result.get("size"),
            "fullPath": full_path
        }
    )

    return result

