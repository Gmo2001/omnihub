import logging
import sys
import os

# Ensure current directory is in path
sys.path.append(os.getcwd())

from app.pipeline.ingestion.sync_drive_to_gcs import Config, get_firestore_client, load_dotenv

# Re-load env just in case
load_dotenv()

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResetSyncState")

def reset_state():
    try:
        # Validate config to ensure env vars are loaded
        # Config.validate() calls getenv, so it should work if env is loaded.
        
        if not Config.TENANT_ID or not Config.ENGAGEMENT_ID:
            logger.error("TENANT_ID or ENGAGEMENT_ID not set in environment.")
            return

        db = get_firestore_client()
        doc_id = f"{Config.TENANT_ID}__{Config.ENGAGEMENT_ID}"
        doc_ref = db.collection("sync_states").document(doc_id)
        
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.delete()
            logger.info(f"Deleted sync state document: {doc_id}")
        else:
            logger.info(f"Sync state document not found: {doc_id}")

    except Exception as e:
        logger.error(f"Error resetting state: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reset_state()
