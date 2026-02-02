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

def process_and_catalog_file(
    user: UserSchema, 
    file_id: str, 
    virtual_path: str = None,
    drive_meta: dict = None # [Opt] Pass metadata to avoid re-fetch
) -> dict:
    """
    단일 파일을 GCS로 스트리밍하고, Firestore에 메타데이터를 등록합니다.
    [Updated] Delta Sync: 변경되지 않은 파일은 건너뜁니다.
    """
    # [Standardization] Ensure ID has prefix (fil_XXX)
    file_id = to_internal_id('fil_', file_id)

    # 0. Fetch Metadata (if not provided)
    if not drive_meta:
        try:
            ds = get_drive_service()
            drive_meta = ds.files().get(
                fileId=file_id.replace("fil_", ""), 
                fields="id, name, modifiedTime, createdTime, mimeType, owners, lastModifyingUser, webViewLink, iconLink, trashed, size"
            ).execute()
        except Exception as e:
            print(f"[Ingest] Failed to fetch meta for {file_id}: {e}")
            raise e

    # 0.5 Delta Sync Check (Time-Traveling)
    current_modified_time = drive_meta.get("modifiedTime")
    doc_ref = db.collection('files').document(file_id)
    doc_snap = doc_ref.get()
    
    if doc_snap.exists:
        stored_data = doc_snap.to_dict()
        stored_modified_time = stored_data.get("driveModifiedTime")
        
        # [Optimized] Skip if timestamps match
        if stored_modified_time == current_modified_time:
            # print(f"[Ingest] Skipped {file_id} (Unchanged)") # Verbose log invalidation
            return {"status": "skipped", "file_id": file_id, "reason": "unchanged"}

    # 1. Stream to GCS
    try:
        # Note: stream_file_to_gcs might fetch meta again, distinct from our check
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
        meta = result.get("metadata", drive_meta) # Fallback to our fetched meta
        
        # Date parsing (ISO to Datetime)
        created_at_dt = None
        if "createdTime" in meta:
            try:
                created_at_dt = datetime.fromisoformat(meta["createdTime"].replace("Z", "+00:00"))
            except: pass

        update_data = {
            "fileId": file_id,
            "fileDeptId": user.department_id, 
            
            # [Fix] Common Rules: CamelCase Keys
            "name": meta.get("name", result.get("file_name")),
            "mimeType": result.get("mime_type"),
            
            "fullPath": full_path,
            
            "gcsUri": result.get("gcs_uri"),
            
            # Additional Drive Meta
            "owners": [owner.get("displayName") for owner in meta.get("owners", [])],
            "lastModifiedBy": meta.get("lastModifyingUser", {}).get("displayName", "Unknown"),
            "webViewLink": meta.get("webViewLink"),
            "iconLink": meta.get("iconLink"),
            
            # Timestamps
            "createdAt": created_at_dt,
            "updatedAt": firestore.SERVER_TIMESTAMP, 
            "driveModifiedTime": current_modified_time, # [Critical] For next Delta Sync
            
            # Status Flags
            "status": "synced",
            "aiStatus": "pending",
            
            "isFolder": False,
            "isFolder": False,
            "trashed": meta.get("trashed", False),
            
            # [Phase 3] Extracted Content Metadata
            "metadata": result.get("internal_metadata", {})
        }

        doc_ref.set(update_data, merge=True)
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
    # 문서가 이미 존재했으면 UPDATE, 아니면 CREATE (최초 수집)
    action_type = ActionType.UPDATE if doc_snap.exists else ActionType.CREATE
    
    log_user_action(
        user=user,
        action=action_type, 
        file_id=file_id,
        success=True,
        details={
            "gcsUri": result.get("gcs_uri"), 
            "size": result.get("size"),
            "fullPath": full_path,
            "deltaParams": {"modifiedTime": current_modified_time}
        }
    )

    return result

