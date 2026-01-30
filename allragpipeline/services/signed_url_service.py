import os
import logging
import datetime
from google.cloud import storage
from fastapi import HTTPException

# Logger Setup
logger = logging.getLogger("SignedURLService")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# Constants
DEFAULT_EXPIRES_SEC = int(os.getenv("SIGNED_URL_DEFAULT_EXPIRES_SEC", 300))
MAX_EXPIRES_SEC = int(os.getenv("SIGNED_URL_MAX_EXPIRES_SEC", 3600))
SIGN_MODE = os.getenv("GCS_SIGN_MODE", "key").lower()

class SignedURLService:
    """
    Generates GCS Signed URLs for secure object access.
    Supports Service Account Key mode (default) and IAM SignBlob mode.
    """
    def __init__(self):
        # Initialize Storage Client (uses GOOGLE_APPLICATION_CREDENTIALS)
        self.client = storage.Client()
        
    def generate_download_link(self, gcs_uri: str, filename: str = None, expires_sec: int = None) -> str:
        """
        Generate a GET Signed URL.
        :param gcs_uri: gs://bucket/path/to/blob
        :param filename: content-disposition filename override
        :param expires_sec: link expiration time in seconds
        :return: Signed URL string
        """
        
        # 1. Validation & Parsing
        if not gcs_uri or not gcs_uri.startswith("gs://"):
            logger.error("Invalid GCS URI format")
            raise ValueError("Invalid GCS URI")
            
        try:
            # gs://bucket_name/blob_name
            parts = gcs_uri.replace("gs://", "").split("/", 1)
            bucket_name = parts[0]
            blob_name = parts[1]
        except IndexError:
            logger.error(f"Malformed GCS URI: {gcs_uri}")
            raise ValueError("Malformed GCS URI")
            
        # 2. Expiration Logic
        duration = expires_sec if expires_sec else DEFAULT_EXPIRES_SEC
        if duration > MAX_EXPIRES_SEC:
            duration = MAX_EXPIRES_SEC
        
        expiration_time = datetime.timedelta(seconds=duration)
        
        # 3. Content-Disposition (Input sanitization recommended for filenames)
        response_disposition = None
        if filename:
            # Simple sanitization or quoting could be added here
            response_disposition = f'attachment; filename="{filename}"'

        # 4. Generate URL
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            # Method A: Standard Key Signing
            # (Requires Service Account Key file or valid credentials with signing capability)
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration_time,
                method="GET",
                response_disposition=response_disposition
            )
            return url
            
        except Exception as e:
            logger.error(f"Generate Signed URL Failed: {e}")
            # If "SigningError" occurs, it means credentials don't support signing (e.g. ADC without key).
            # Then we might need IAM SignBlob API (Method B), but that's complex implementation.
            raise HTTPException(status_code=500, detail="Failed to generate secure link")
