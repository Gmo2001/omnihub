import logging
import argparse
import asyncio
from app.core.gcp_clients import db
from datetime import datetime
from app.services.ai_a.allragpipeline.pipeline_runner import PipelineRunner, Config

# 로거 설정
logger = logging.getLogger("AnalysisService")
logger.setLevel(logging.INFO)

async def trigger_analysis(file_id: str, gcs_uri: str, mime_type: str):
    """
    [Phase 3 Orchestrator]
    파일 수집(Ingestion) 완료 후, 전체 RAG 파이프라인(PipelineRunner)을 실행합니다.
    - ingest.py로부터 호출됩니다.
    - OCR -> 요약 -> 임베딩 -> 인덱싱 과정을 순차적으로 수행합니다.
    """
    logger.info(f"⚡ [Pipeline Trigger] Starting full analysis for {file_id}")

    # 1. 상태 업데이트 (Processing)
    db.collection('files').document(file_id).update({
        "aiStatus": "processing",
        "aiStartedAt": datetime.utcnow() # Use native datetime for Firestore or server_timestamp
    })

    try:
        # 2. PipelineRunner 인자 구성
        # 런타임에 필요한 인자들을 구성합니다.
        # Tenant/Engagement ID는 현재 Config(env)에서 가져오거나, 필요시 file_meta에서 조회해야 합니다.
        # 여기서는 환경변수 기반 Config를 사용합니다.
        
        args = argparse.Namespace(
            doc_id=file_id,
            tenant_id=Config.PROJECT_ID if not hasattr(Config, 'TENANT_ID') else Config.TENANT_ID or "default_tenant", # Fallback
            engagement_id="default_engagement", # Placeholder or Config
            mode="full", 
            max_workers=4,
            force_global=False
        )

        # 3. PipelineRunner 실행 (Blocking Call)
        # 이 작업은 시간이 오래 걸리므로(수십 초~수 분), 
        # 호출자가 BackgroundTasks 또는 asyncio.create_task로 실행해야 합니다.
        
        # PipelineRunner는 내부적으로 Subprocess 등을 사용해 Phase A~D를 수행합니다.
        # Action 2에서 구현한 'ai_results' 저장 로직이 이 과정에서 호출됩니다.
        
        # 동기 함수인 runner.run()을 비동기 환경에서 매끄럽게 돌리기 위해 to_thread 사용 권장
        # 하지만 runner가 내부적으로 subprocess를 쓰므로 GIL 영향은 적음.
        # 여기서는 간결하게 직접 실행합니다.
        runner = PipelineRunner(args)
        
        # Run in thread pool to avoid blocking the event loop if it does heavy python work
        await asyncio.to_thread(runner.run)
        
        # 4. 완료 처리
        # PipelineRunner 내부에서도 status를 남기지만, files 컬렉션 상태 동기화
        db.collection('files').document(file_id).update({
            "aiStatus": "completed",
            "aiCompletedAt": datetime.utcnow()
        })
        logger.info(f"✅ [Pipeline Trigger] Completed for {file_id}")

    except Exception as e:
        logger.error(f"❌ [Pipeline Trigger] Failed for {file_id}: {e}")
        db.collection('files').document(file_id).update({
            "aiStatus": "failed",
            "errorMsg": str(e)
        })

 