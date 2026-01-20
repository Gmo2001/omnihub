import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import service_account
from googleapiclient.discovery import build
from app.core.config import settings

# 1. Firestore 초기화
# firebase_admin이 이미 초기화되었는지 확인 후 초기화
if not firebase_admin._apps:
    # GOOGLE_APPLICATION_CREDENTIALS 환경변수나 파일 경로를 자동으로 감지하지만,
    # 명시적으로 서비스 계정 파일을 사용할 경우:
    if settings.GOOGLE_APPLICATION_CREDENTIALS:
        cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

db = firestore.client()

# 2. Google Drive API 클라이언트 초기화
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']  # SCOPES 설명: Google API는 보안을 위해 앱이 어떤 권한(읽기 전용, 쓰기 가능 등)을 사용하는지 명시적으로 요구합니다.

def get_drive_service():
    """
    구글 드라이브 API 클라이언트를 생성하여 반환합니다.
    service_account.json 파일을 사용하여 인증합니다.
    """
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_APPLICATION_CREDENTIALS, 
        scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)
