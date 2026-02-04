
import asyncio
import argparse
import logging
import sys
import os

# --- Path Setup ---
# Add 'backend' root to sys.path to allow imports like 'app.rag.orchestrator'
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_root = os.path.abspath(os.path.join(current_dir, "../../"))
if backend_root not in sys.path:
    sys.path.append(backend_root)

# [Local Run] Load .env explicitly for standalone script execution
from dotenv import load_dotenv
load_dotenv(os.path.join(backend_root, ".env")) # Load .env from root

from app.core.config import settings
from app.rag.orchestrator import PipelineOrchestrator

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAG-Runner")

async def run_job(doc_id: str, gcs_uri: str = None, mime_type: str = None):
    """
    Manual Pipeline Runner Entry Point (Dev/Emergency)
    """
    logger.info(f"🚀 [Job] Starting Pipeline Job for DocID: {doc_id}")
    
    orchestrator = PipelineOrchestrator()
    try:
        await orchestrator.run_pipeline(doc_id, gcs_uri, mime_type)
        logger.info(f"✅ [Job] Pipeline Job Completed for DocID: {doc_id}")
    except Exception as e:
        logger.error(f"❌ [Job] Pipeline Job Failed: {e}", exc_info=True)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Omnihub RAG Pipeline Runner (Manual Trigger)")
    parser.add_argument("--doc_id", type=str, required=True, help="Firestore Document ID")
    parser.add_argument("--gcs_uri", type=str, required=False, help="GCS URI for DocAI (Optional if already processed)")
    parser.add_argument("--mime_type", type=str, required=False, help="MimeType (Optional)")
    
    args = parser.parse_args()
    
    asyncio.run(run_job(args.doc_id, args.gcs_uri, args.mime_type))

if __name__ == "__main__":
    main()
