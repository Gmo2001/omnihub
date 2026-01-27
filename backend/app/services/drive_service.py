import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage
from app.models.user import UserSchema
from app.core.config import settings
from fastapi import HTTPException
from google.auth.transport.requests import Request
import uuid
from app.core.gcp_clients import db
from app.models.watch import WatchChannelSchema
from datetime import datetime
import time

# GCS Configurations
GCS_BUCKET_NAME = f"{settings.PROJECT_ID}-raw-files" # e.g. "omnihub-raw-files"
# Note: Bucket Name should be globally unique. Using PROJECT_ID prefix is a good practice.
# If PROJECT_ID is not set in config defaults, retrieval might fail if not in env. 
# We'll assume PROJECT_ID is reliable or handle it.

def get_user_drive_service(user: UserSchema):
    """
    Constructs a Google Drive Resource object using the user's stored tokens.
    Handles token refresh if necessary.
    """
    if not user.google_access_token:
        raise HTTPException(status_code=401, detail="User has not connected Google Drive")

    creds = Credentials(
        token=user.google_access_token,
        refresh_token=user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # TODO: Update new token in Firestore (Optional optimization, but good for consistency)

    return build('drive', 'v3', credentials=creds)

def stream_file_to_gcs(user: UserSchema, file_id: str):
    """
    Streams a file from the User's Google Drive to a GCS Bucket.
    Returns the GCS URI.
    """
    drive_service = get_user_drive_service(user)
    
    # 1. Get File Metadata
    try:
        file_meta = drive_service.files().get(
            fileId=file_id, 
            fields="id, name, mimeType, size"
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"File not found in Drive: {str(e)}")

    file_name = file_meta.get('name')
    mime_type = file_meta.get('mimeType')
    
    # Check for Google Workspace files (Docs/Sheets)
    if mime_type.startswith("application/vnd.google-apps"):
        # We must export them. For simplicity, export Docs to PDF.
        # This is a policy decision. 
        # Plan says "Ingestion". PDF is safest for DocAI.
        if "document" in mime_type:
            export_mime = "application/pdf"
            file_ext = ".pdf"
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
             # Skip or handle Sheets/Slides later
             # For now, only allow PDF/Docs
             raise HTTPException(status_code=400, detail=f"Unsupported Workspace file type: {mime_type}")
    else:
        # Binary download for regular files (PDF, JPG, etc.)
        request = drive_service.files().get_media(fileId=file_id)
        file_ext = "" 

    # 2. Prepare GCS Upload
    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    
    # Path: raw/{user_uid}/{file_id}/{filename}
    blob_name = f"raw/{user.uid}/{file_id}/{file_name}{file_ext}"
    blob = bucket.blob(blob_name)

    # 3. Stream Transfer (Download -> Upload)
    # Using a memory buffer. For very large files, this might consume memory.
    # But Cloud Run has 2GB+ usually. For <500MB files, BytesIO is okay.
    # For strictly strictly streaming without holding all in memory, we need a custom generator or temp file.
    # Given requirements "Streaming", let's try to be efficient.
    # But Blob.upload_from_file expects a file-like object.
    
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        # logging.info(f"Download {int(status.progress() * 100)}%.")

    fh.seek(0)
    
    # Upload to GCS
    blob.upload_from_file(fh, content_type=mime_type)
    
    gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_name}"
    return {
        "gcs_uri": gcs_uri,
        "file_name": file_name,
        "mime_type": mime_type,
        "size": file_meta.get('size')
    }

async def register_user_watch(user: UserSchema, base_url: str):
    """
    사용자의 Google Drive에 대한 푸시 알림 채널(Webhook)을 등록합니다.
    이것이 '자동 감시(Auto-Watch)' 기능의 핵심입니다.
    """
    try:
        drive_service = get_user_drive_service(user)
        
        # 0. 중복 방지 로직 (Optimization)
        # 이미 해당 유저의 유효한 채널이 있는지 DB에서 검색
        existing_channels = db.collection('watch_channels').where('user_email', '==', user.email).stream()
        
        current_time_ms = int(time.time() * 1000)
        valid_until_threshold = current_time_ms + (24 * 60 * 60 * 1000) # 최소 24시간 이상 남았는지 확인

        for doc in existing_channels:
            data = doc.to_dict()
            exp = data.get('expiration', 0)
            
            # 1. 만료 시간이 넉넉히 남았다면 -> 재등록 스킵 (Idempotency)
            if exp > valid_until_threshold:
                print(f"[Auto-Watch] 이미 유효한 채널이 존재합니다. (ID: {doc.id}, 만료: {exp}) -> 등록 스킵")
                return # 아무것도 안 하고 종료 (Best Case)
            
            # 2. 만료되었거나 곧 만료됨 -> 기존 채널 정리 (Cleanup)
            print(f"[Auto-Watch] 만료 임박/만료된 채널 정리: {doc.id}")
            try:
                # 구글에 stop 요청 (Resource ID 필요)
                # 만료된 채널이라 stop이 실패할 수도 있지만 시도함
                resource_id = data.get('resource_id')
                if resource_id:
                    drive_service.channels().stop(body={'id': doc.id, 'resourceId': resource_id}).execute()
            except Exception as stop_error:
                print(f"[Auto-Watch] 기존 채널 Stop 실패 (무시됨): {stop_error}")
            
            # DB에서 삭제
            db.collection('watch_channels').document(doc.id).delete()


        # 1. Webhook URL 구성
        # base_url 예시: "https://omnihub-backend-xyz.a.run.app"
        webhook_url = f"{base_url.rstrip('/')}/webhook/drive"
        
        # 2. Start Page Token 발급 (감시 시작점)
        token_response = drive_service.changes().getStartPageToken().execute()
        start_page_token = token_response.get('startPageToken')
        
        # 3. 채널 ID 생성 및 요청 본문 구성
        channel_id = str(uuid.uuid4())
        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            # [Optional] token 필드를 추가하여 보안 강화 가능 (구글이 되돌려줌)
            # "token": "security-token" 
        }
        
        # 4. Watch 요청 실행
        print(f"[Auto-Watch] 새 감시 채널 생성 요청: {user.email} -> {webhook_url}")
        response = drive_service.changes().watch(body=body, pageToken=start_page_token).execute()
        
        # 5. DB에 채널 정보 저장 (watch_channels 컬렉션)
        watch_data = WatchChannelSchema(
            channel_id=channel_id,
            resource_id=response['resourceId'],
            user_email=user.email,
            user_uid=user.uid,
            webhook_url=webhook_url,
            expiration=int(response.get('expiration', 0))
        )
        
        db.collection('watch_channels').document(channel_id).set(watch_data.dict())
        print(f"[Auto-Watch] 채널 등록 성공: {channel_id}")
        
    except Exception as e:
        print(f"[Auto-Watch] 감시 등록 실패 ({user.email}): {e}")
        # 로그인 프로세스를 방해하지 않기 위해 로그만 남기고 넘어감
