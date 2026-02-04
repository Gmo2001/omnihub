import os
import logging
import argparse
import time
from google.cloud import firestore
from pipeline_runner import PipelineRunner
from sync_drive_to_gcs import DriveSyncAgent, Config as SyncConfig

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BulkRunner")

def run_bulk_pipeline(tenant_id: str, engagement_id: str, mode: str = "full"):
    # 0. 환경 설정 및 동기화 (Phase 1)
    # CLI 인자로 받은 값으로 환경 변수 및 Config 강제 설정
    os.environ["TENANT_ID"] = tenant_id
    os.environ["ENGAGEMENT_ID"] = engagement_id
    SyncConfig.TENANT_ID = tenant_id
    SyncConfig.ENGAGEMENT_ID = engagement_id

    logger.info("=" * 50)
    logger.info("🚀 [Phase 1] Google Drive 동기화 시작...")
    try:
        agent = DriveSyncAgent()
        agent.run()
        logger.info("✅ [Phase 1] 동기화 완료")
    except Exception as e:
        logger.error(f"❌ [Phase 1] 동기화 실패 (계속 진행): {str(e)}")

    logger.info("=" * 50)
    logger.info("🚀 [Phase 2] 문서 일괄 처리 시작...")

    db = firestore.Client()
    
    # 1. 해당 테넌트/인게이지먼트에서 아직 승인되지 않은(PENDING) 문서들만 추출
    # 또는 동기화는 되었으나(active=True), RAG 처리가 안 된 문서들을 찾을 수도 있음.
    # 여기서는 "review_status"보다는 "sync_drive_to_gcs"에 의해 생성된 모든 active 문서를 대상으로 하되,
    # 필요하다면 특정 조건을 추가. 
    # 일단 'active=True'인 모든 문서를 가져오기로 함.
    # 하지만 이미 처리된 문서를 건너뛰려면? -> pipeline_runs 기록을 확인해야 하지만 너무 느림.
    # 따라서 mode="resume"를 활용하여 PipelineRunner에게 맡기거나, 
    # doc_runs 컬렉션을 확인하여 성공한 문서는 패스하는 로직 추가 가능.
    # 여기서는 단순하게 "모든 active 문서"를 대상으로 하되, PipelineRunner 실패 시 계속 진행하도록 함.
    
    # 1. 'documents' 컬렉션에서 해당 범위의 모든 문서를 가져옴
    docs_ref = (db.collection("documents") 
                 .where("tenant_id", "==", tenant_id) 
                 .where("engagement_id", "==", engagement_id) 
                 .where("active", "==", True) 
                 .stream())

    all_docs = [d for d in docs_ref]
    total_found = len(all_docs) 
    
    # 2. 상태에 따른 분류
    pending_ids = []
    approved_count = 0
    
    for d in all_docs:
        data = d.to_dict()
        if data.get("review_status") == "APPROVED":
            approved_count += 1 
        else:
            pending_ids.append(d.id)

    to_process = len(pending_ids)

    # 3. 직관적인 요약 로그 출력
    logger.info("=" * 50)
    logger.info(f"📊 [Omnihub 파이프라인 대량 처리 요약]")
    logger.info(f" - 전체 발견 문서: {total_found}개")
    logger.info(f" - 이미 완료(APPROVED): {approved_count}개 (스킵)")
    logger.info(f" - 신규 처리 대상: {to_process}개")
    logger.info("=" * 50)

    if to_process == 0:
        logger.info("✅ 모든 문서가 최신 상태입니다. 처리를 종료합니다.")
        return

    # 4. 순차 처리 시작
    for i, doc_id in enumerate(pending_ids, 1):
        try:
            logger.info(f"\n[{i}/{to_process}] 문서 처리 시작: {doc_id}")
            
            # argparse.Namespace 흉내내기 (PipelineRunner가 args 객체를 받으므로)
            class Args:
                def __init__(self, d, t, e, m):
                    self.doc_id = d
                    self.tenant_id = t
                    self.engagement_id = e
                    self.mode = m
                    self.max_workers = 4
                    self.force_global = False
            
            args = Args(doc_id, tenant_id, engagement_id, mode)

            # 기존 PipelineRunner 인스턴스 생성 및 실행
            runner = PipelineRunner(args)
            runner.run()
            
            logger.info(f"✅ 문서 처리 완료: {doc_id}")
            
            # (옵션) 과부하 방지용 짧은 대기
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"❌ 문서 처리 실패 ({doc_id}): {str(e)}")
            # 실패해도 다음 문서 진행
            continue 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant_id", required=True)
    parser.add_argument("--engagement_id", required=True)
    parser.add_argument("--mode", default="full")
    
    args = parser.parse_args()
    
    run_bulk_pipeline(args.tenant_id, args.engagement_id, args.mode)
