import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage
from app.models.user import UserSchema
from app.core.config import settings
from fastapi import HTTPException
from google.auth.transport.requests import Request

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
