import asyncio
import logging
import sys
import os

# Backend 경로 추가 (모듈 import 위해)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings

# Force Load Credentials for Local Test
# Vertex AI SDK sometimes prioritizes ADC (gcloud auth) over env vars if not explicitly set early.
import os
from dotenv import load_dotenv
load_dotenv()

if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    print(f"🔑 Using Service Account: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
else:
    print("⚠️ GOOGLE_APPLICATION_CREDENTIALS not found in .env")

from app.rag.orchestrator import PipelineOrchestrator

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestRAG")

async def test_pipeline(doc_id: str):
    print(f"\n🚀 [TEST] RAG Pipeline Testing for Doc ID: {doc_id}")
    print(f"   Project: {settings.PROJECT_ID}")
    print(f"   Database: {settings.FIRESTORE_DATABASE}")
    
    orchestrator = PipelineOrchestrator()
    
    # 1. Run Pipeline
    # GCS URI, MimeType은 이미 DocAI가 돌았다고 가정하고 생략하거나, 
    # 테스트 파일이 있다면 넣어줄 수 있음.
    # 여기서는 '이미 DocAI 완료된 상태'에서 이후 파이프라인이 잘 도는지 테스트.
    
    logger.info("Calling orchestrator.run_pipeline()...")
    await orchestrator.run_pipeline(doc_id)
    
    logger.info("Test finished. Check Firestore logs for details.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_rag_pipeline.py <doc_id>")
        sys.exit(1)
        
    target_doc_id = sys.argv[1]
    asyncio.run(test_pipeline(target_doc_id))
