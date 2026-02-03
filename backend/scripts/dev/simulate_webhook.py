import sys
import os
import time
import json
import logging
import asyncio
from datetime import datetime

# 1. 경로 설정 (backend 폴더 기준)
sys.path.append(os.getcwd())

# 환경 변수 로드 (자격 증명 확인용)
from dotenv import load_dotenv
load_dotenv()

from app.core.gcp_clients import get_drive_service, db
from app.core.config import settings
from app.models.user import UserSchema
from app.services.ingestion_service import process_and_catalog_file
from app.rag.orchestrator import PipelineOrchestrator

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimulateWebhook")

# ==========================================
# 👇 테스트 설정
# ==========================================
# 사용자가 요청한 특정 테스트 폴더 ID
TARGET_FOLDER_ID = "1gH1nvnYFLPNTutPMhLXcKKZ02zpM0L67" 

USER_EMAIL = "edu_147@omnihub.com" # 로그용 가짜 이메일
# ==========================================

def run_async(coro):
    """동기 함수 내에서 비동기 코루틴 실행을 위한 헬퍼"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

def main():
    print(f"\n👀 [Watcher] 드라이브 감시 시작...")
    print(f"📂 대상 폴더 ID: {TARGET_FOLDER_ID}")
    print("   (드라이브에 파일을 업로드하면 Ingestion -> RAG Pipeline이 자동 실행됩니다.)")
    print("   (종료하려면 Ctrl+C를 누르세요)\n")

    # 1. 서비스 계정 인증 확인
    try:
        drive_service = get_drive_service()
    except Exception as e:
        print(f"❌ 인증 실패: service_account.json 확인 필요 ({e})")
        return

    # 2. 파이프라인 실행을 위한 가짜 관리자 유저 생성
    dummy_user = UserSchema(
        userId="usr_watcher_001",
        email=USER_EMAIL,
        displayName="Watcher Bot",
        role="admin",
        google_access_token="dummy", 
        google_refresh_token="dummy",
        department="Security Ops"
    )

    # 3. Orchestrator 초기화
    orchestrator = PipelineOrchestrator()

    # 4. 기준점(Start Page Token) 가져오기
    token_response = drive_service.changes().getStartPageToken().execute()
    saved_start_page_token = token_response.get('startPageToken')
    
    print(f"✅ 기준 토큰 획득 완료: {saved_start_page_token}")
    print("⏳ 변경 사항 대기 중...\n")

    try:
        while True:
            # 5. 변경사항 확인 (Polling)
            response = drive_service.changes().list(
                pageToken=saved_start_page_token,
                spaces='drive',
                fields='newStartPageToken, nextPageToken, changes(fileId, file(id, name, mimeType, parents, trashed))',
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()

            changes = response.get('changes', [])
            
            if response.get('newStartPageToken'):
                saved_start_page_token = response.get('newStartPageToken')

            # 6. 변경사항이 감지되면 처리 시작
            for change in changes:
                file_id = change.get('fileId')
                file_meta = change.get('file')

                if not file_meta or file_meta.get('trashed'):
                    continue

                parents = file_meta.get('parents', [])
                if TARGET_FOLDER_ID not in parents:
                    continue

                print("="*60)
                print(f"🚨 [감지] 파이프라인 트리거! ({datetime.now().strftime('%H:%M:%S')})")
                print(f"📄 파일명: {file_meta.get('name')}")
                print(f"🆔 File ID: {file_id}")
                
                try:
                    # --- Step 1: Ingestion (GCS Stream & Metadata) ---
                    print("\n🚀 [Step 1] Ingestion (Drive -> GCS)...")
                    ingest_result = process_and_catalog_file(
                        user=dummy_user,
                        file_id=file_id,
                        drive_meta=file_meta
                    )
                    
                    # Ingest 결과에서 정보 추출
                    internal_id = ingest_result.get("file_id") or f"fil_{file_id}" # 만약 file_id가 없으면 fallback
                    gcs_uri = ingest_result.get('gcs_uri')
                    mime_type = ingest_result.get('mime_type')
                    
                    print(f"✅ [Ingest 완료] ID: {internal_id}")
                    print(f"   GCS URI: {gcs_uri}")

                    # --- Step 2: RAG Pipeline Orchestration ---
                    print("\n🎼 [Step 2] RAG Pipeline Orchestration (Full Flow)...")
                    print(f"   ▶️ PipelineOrchestrator 실행 중...")
                    
                    # Async Pipeline 실행
                    run_async(orchestrator.run_pipeline(
                        file_id=internal_id, 
                        gcs_uri=gcs_uri, 
                        mime_type=mime_type
                    ))
                    
                    print("\n✅ [Pipeline 완료] End-to-End 처리가 끝났습니다.")
                    
                    # --- Step 3: 최종 검증 (Verification) ---
                    print("\n🔍 [검증] 최종 데이터 확인 (Firestore)...")
                    
                    # 1) Profile
                    profile_snap = db.collection('profiles').document(internal_id).get()
                    has_profile = profile_snap.exists
                    print(f"   - Profile 생성: {'✅ Success' if has_profile else '❌ Failed'}")

                    # 2) Document (Summary & Meta)
                    doc_snap = db.collection('documents').document(internal_id).get()
                    if doc_snap.exists:
                        data = doc_snap.to_dict()
                        print(f"   - Document 생성: ✅ Success")
                        print(f"     📜 Title: {data.get('title')}")
                        print(f"     🛡️ Security: {data.get('security_level')}")
                        print(f"     📝 Summary: {str(data.get('card_summary', {}).get('l3'))[:50]}...")
                    else:
                         print(f"   - Document 생성: ❌ Failed (문서 요약/분류 실패)")

                    # 3) Vector Status
                    print(f"   - Vector DB Upsert: (로그 상에서 'Vector Upsert' 단계를 확인하세요)")

                except Exception as e:
                    print(f"💥 오류 발생: {e}")
                    import traceback
                    traceback.print_exc()

                print("="*60 + "\n")
                print("⏳ 다음 변경 대기 중...")

            time.sleep(3)

    except KeyboardInterrupt:
        print("\n🛑 감시 종료")

if __name__ == "__main__":
    main()