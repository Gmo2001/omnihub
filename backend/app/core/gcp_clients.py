import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import storage, firestore as google_firestore
from google.oauth2 import service_account
from googleapiclient.discovery import build
from functools import lru_cache
from typing import Optional, Any
import logging
import os

from app.core.config import settings

logger = logging.getLogger("GCP_Clients")

# [Global Cache] - Valid during process lifetime
_firebase_app = None

def get_firebase_app():
    """
    Initializes Firebase Admin SDK (Lazy Loading).
    - Uses GOOGLE_APPLICATION_CREDENTIALS if set (Local).
    - Uses ADC (Application Default Credentials) if not set (Cloud Run).
    """
    global _firebase_app
    if _firebase_app:
        return _firebase_app

    # idempotency check (firebase_admin throws if init twice)
    if firebase_admin._apps:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app

    try:
        if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
            logger.info(f"🔥 [Firebase] Initializing with Key File: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
            cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
            _firebase_app = firebase_admin.initialize_app(cred)
        else:
            logger.info("🔥 [Firebase] Initializing with ADC (Cloud Run Environment)")
            _firebase_app = firebase_admin.initialize_app()
            
        return _firebase_app
    except Exception as e:
        logger.error(f"❌ [Firebase] Init Failed: {e}")
        raise e

@lru_cache()
def get_firestore_client() -> google_firestore.Client:
    """
    Returns a Google Cloud Firestore Client (Native).
    Preferred over Firebase Admin for backend operations because it supports async better in newer libs
    and is standard for Server-side.
    """
    # Initialize Firebase App first to ensure auth context is ready (if using firebase-admin elsewhere)
    get_firebase_app() 
    
    logger.info("📚 [Firestore] Creating Client...")
    try:
        # Google Native Client (Better for typed usage)
        # It automatically finds credentials via ADC or GOOGLE_APPLICATION_CREDENTIALS env var
        db = google_firestore.Client(
            project=settings.PROJECT_ID,
            database=settings.FIRESTORE_DATABASE
        )
        return db
    except Exception as e:
        logger.error(f"❌ [Firestore] Connection Failed: {e}")
        raise e

@lru_cache()
def get_storage_client() -> storage.Client:
    """
    Returns a Google Cloud Storage Client.
    """
    logger.info("📦 [Storage] Creating Client...")
    if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
         return storage.Client.from_service_account_json(settings.GOOGLE_APPLICATION_CREDENTIALS)
    
    return storage.Client(project=settings.PROJECT_ID)

def get_drive_service(user_creds=None) -> Any:
    """
    Returns a Google Drive API Service.
    Args:
        user_creds: Optional. If provided, creates service as User.
                    If None, tries to create service as Service Account (Domain-Wide or Robot).
    """
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    
    if user_creds:
        return build('drive', 'v3', credentials=user_creds)

    # Service Account Mode
    if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS, 
            scopes=SCOPES
        )
        return build('drive', 'v3', credentials=creds)
    
    # ADC Mode for Drive? 
    # Usually ADC works for Drive too if the SA has scopes.
    # But often need explicit scopes.
    import google.auth
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ [Drive] Failed to init Drive Service: {e}")
        raise e

# [Restored] Global DB Object for backward compatibility
# WARNING: This causes side-effects on import (authenticates immediately)
if not firebase_admin._apps:
    if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
        firebase_admin.initialize_app(cred)
    else:
        # Cloud Run (ADC)
        firebase_admin.initialize_app()

db = firestore.client()
