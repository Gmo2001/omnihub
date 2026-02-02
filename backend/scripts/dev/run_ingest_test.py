import sys
import os
import asyncio

# 1. 파이썬이 'app' 폴더를 찾을 수 있게 경로 설정
sys.path.append(os.getcwd())

from app.models.user import UserSchema
from app.services.ingestion_service import process_and_catalog_file

# 테스트 설정
TARGET_FILE_ID = "13467912568799186265"  # <-- 테스트할 구글 드라이브 파일 ID (URL의 ?id= 뒤에 있는 값)
USER_EMAIL = "[EMAIL_ADDRESS]"

def main():
    print(f"🚀 Ingestion 테스트 시작: {TARGET_FILE_ID}")

    # 2. 가짜 유저 객체 생성 (함수가 UserSchema 객체를 요구하므로)
    # 실제로는 DB에서 가져오지만, 테스트를 위해 임의로 만듭니다.
    dummy_user = UserSchema(
        userId="usr_test_123",
        email=USER_EMAIL,
        displayName="Test Runner",
        department="IT Team",
        department_id="DEPT_IT",
        role="admin",
        # 주의: 로컬 테스트 시 구글 API 호출 권한이 필요하다면 
        # 실제 작동하는 google_access_token이 필요할 수 있습니다.
        # 서비스 계정(service_account.json)만으로 충분한 로직이라면 비워둬도 됩니다.
        google_access_token="dummy_token", 
        google_refresh_token="dummy_refresh"
    )

    try:
        # 3. Ingestion 서비스 호출
        result = process_and_catalog_file(
            user=dummy_user,
            file_id=TARGET_FILE_ID
        )
        
        print("\n✅ 성공적으로 처리되었습니다!")
        print("="*30)
        print(f"📂 파일명: {result.get('file_name', 'N/A')}")
        print(f"💾 GCS 경로: {result.get('gcs_uri')}")
        print(f"📄 MIME 타입: {result.get('mime_type')}")
        print("="*30)

    except Exception as e:
        print(f"\n❌ 에러 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()