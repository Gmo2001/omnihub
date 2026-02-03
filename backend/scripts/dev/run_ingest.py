
import asyncio
import os
import sys

# 프로젝트 루트 경로 설정
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.models.user import UserSchema
from app.services.ingestion_service import process_and_catalog_file
from app.core.config import settings

def main():
    print("🚀 [Ingest-Test] 파일 수집(Ingestion) 시뮬레이션 시작")
    print(f"   - Project: {settings.PROJECT_ID}")
    
    # 1. 사용할 파일 ID (테스트용)
    # 실제 존재하는 구글 드라이브 파일 ID를 넣어야 합니다. (권한이 있는 파일)
    TEST_FILE_ID = "1LCrJjKBozP8-qfFZKqXFjt8U-mkYERwO"  # POS 유지보수 계약서

    # 2. 가짜 사용자 생성 (Ingestion 함수가 UserSchema를 필요로 함)
    # 'dummy' 토큰을 넣으면 drive_service.py에서 SA(서비스 계정)를 사용하도록 수정된 로직을 활용합니다.
    mock_user = UserSchema(
        user_id="usr_watcher_001",
        email="watcher@example.com", 
        name="Watcher Bot",
        display_name="Watcher Bot", # 필수 필드 (displayName alias)
        google_access_token="dummy_for_sa_test", # 중요: SA 사용 트리거
        department_id="dept_test"
    )

    try:
        # 3. Ingest 실행
        print(f"   - Target File: {TEST_FILE_ID}")
        print("   ⏳ GCS 업로드 및 DB 등록 중...")
        
        result = process_and_catalog_file(mock_user, TEST_FILE_ID)
        
        print("\n✅ Ingestion 완료!")
        print("---------------------------------------------------")
        print(f" File ID    : {result.get('file_id')}")
        print(f" File Name  : {result.get('file_name')}")
        print(f" GCS URI    : {result.get('gcs_uri')}")
        print(f" Mime Type  : {result.get('mime_type')}")
        print("---------------------------------------------------")

        # 4. (선택사항) 여기서 바로 파이프라인 트리거도 가능하지만, 
        #    사용자 요청대로 Ingest만 먼저 확인합니다.
        
    except Exception as e:
        print(f"\n❌ Ingestion 실패: {e}")

if __name__ == "__main__":
    main()
