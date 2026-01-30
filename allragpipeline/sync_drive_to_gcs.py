import os
import sys
import argparse
import json
import time
import hashlib
import logging
import datetime
import traceback
import io
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from google.oauth2 import service_account
from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage
from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    GCS_PREFIX = os.getenv("GCS_PREFIX", "omnihub")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    DRIVE_ROOT_ID = os.getenv("DRIVE_ROOT_FOLDER_ID")
    DRIVE_QUERY = os.getenv("DRIVE_QUERY")
    
    # Auth
    AUTH_MODE = os.getenv("DRIVE_OAUTH_MODE", "sa").lower() # sa, dwd, oauth
    SA_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    IMPERSONATE_EMAIL = os.getenv("DRIVE_IMPERSONATE_EMAIL")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.PROJECT_ID: missing.append("GCP_PROJECT_ID")
        if not cls.GCS_BUCKET: missing.append("GCS_BUCKET")
        if not cls.TENANT_ID: missing.append("TENANT_ID")
        if not cls.ENGAGEMENT_ID: missing.append("ENGAGEMENT_ID")
        
        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")

# --- Logger Setup ---
def setup_logger():
    logger = logging.getLogger("DriveSync")
    logger.setLevel(Config.LOG_LEVEL)
    
    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(Config.LOG_LEVEL)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(ch)
    
    return logger

logger = setup_logger()

# --- Helper Functions ---

def generate_doc_id(tenant_id: str, engagement_id: str, drive_file_id: str) -> str:
    """doc_id = SHA256(tenant_id + engagement_id + drive_file_id)"""
    raw_key = f"{tenant_id}:{engagement_id}:{drive_file_id}"
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

def get_current_timestamp_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

# --- Service Wrappers ---

def get_drive_service():
    """Drive API Service 빌드. Auth 모드에 따라 처리."""
    scopes = ['https://www.googleapis.com/auth/drive.readonly']
    
    creds = None
    
    if Config.AUTH_MODE == 'dwd':
        # Domain-Wide Delegation
        if not Config.SA_KEY_PATH:
            raise ValueError("DWD 모드 사용 시 GOOGLE_APPLICATION_CREDENTIALS 경로가 필요합니다.")
        if not Config.IMPERSONATE_EMAIL:
            raise ValueError("DWD 모드 사용 시 DRIVE_IMPERSONATE_EMAIL이 필요합니다.")
            
        creds = service_account.Credentials.from_service_account_file(
            Config.SA_KEY_PATH, scopes=scopes
        )
        creds = creds.with_subject(Config.IMPERSONATE_EMAIL)
        logger.info(f"DWD 인증 사용: {Config.IMPERSONATE_EMAIL} 위임")
        
    elif Config.AUTH_MODE == 'sa':
        # 일반 Service Account
        if Config.SA_KEY_PATH:
            creds = service_account.Credentials.from_service_account_file(
                Config.SA_KEY_PATH, scopes=scopes
            )
            logger.info("Service Account Key 파일 인증 사용")
        else:
            creds, _ = default()
            logger.info("Application Default Credentials (ADC) 인증 사용")
    
    else:
        # OAuth 등 기타 (여기서는 간단히 ADC로 fallback 또는 구현 필요)
        # 실제 로컬 OAuth Flow는 google-auth-oauthlib 필요
        creds, _ = default()
        logger.info("Default 인증 모드 사용")

    return build('drive', 'v3', credentials=creds)

def get_storage_client():
    return storage.Client(project=Config.PROJECT_ID)

def get_firestore_client():
    return firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)

# --- Core Logic ---

class DriveSyncAgent:
    def __init__(self):
        self.run_id = f"run_{int(time.time())}"
        self.db = get_firestore_client()
        self.storage = get_storage_client()
        self.drive_service = get_drive_service()
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        
        self.sync_state_ref = self.db.collection("sync_states").document(f"{Config.TENANT_ID}__{Config.ENGAGEMENT_ID}")
        self.run_ref = self.db.collection("sync_runs").document(self.run_id)
        
        self.stats = {
            "total_found": 0,
            "synced": 0,
            "failed": 0,
            "skipped": 0,
            "deleted": 0,
            "start_time": get_current_timestamp_iso(),
            "end_time": None
        }
        self.sync_results = [] # 간단한 요약 리스트

    def get_last_sync_state(self) -> dict:
        doc = self.sync_state_ref.get()
        if doc.exists:
            return doc.to_dict()
        return {}

    def save_sync_state(self, last_modified_time: str):
        """마지막 동기화 시간 갱신"""
        state = {
            "last_sync_time": last_modified_time,
            "last_run_id": self.run_id,
            "updated_at": get_current_timestamp_iso()
        }
        self.sync_state_ref.set(state, merge=True)
        logger.info(f"Sync State 갱신: {last_modified_time}")

    def fetch_all_files_recursive(self, folder_id: str, last_sync_time: Optional[str] = None) -> List[Dict]:
        """폴더는 무조건 탐색하고, 파일만 시간 필터를 적용합니다."""
        all_files = []
        page_token = None
        
        # 쿼리: 해당 폴더 내의 모든 파일과 폴더를 가져옴 (시간 필터 제외)
        q = f"'{folder_id}' in parents and (trashed = true or trashed = false)"

        while True:
            response = self.drive_service.files().list(
                q=q,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, trashed, parents, size)",
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            for f in response.get('files', []):
                if f['mimeType'] == 'application/vnd.google-apps.folder':
                    # 폴더는 무조건 안으로 파고듭니다.
                    logger.info(f"하위 폴더 탐색 중: {f['name']}")
                    all_files.extend(self.fetch_all_files_recursive(f['id'], last_sync_time))
                else:
                    # 파일인 경우에만 시간 필터를 체크합니다.
                    if last_sync_time:
                        if f.get('modifiedTime') > last_sync_time:
                            all_files.append(f)
                    else:
                        all_files.append(f)
            
            page_token = response.get('nextPageToken')
            if not page_token:
                break
                
        return all_files

    def run(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return

        logger.info(f"동기화 시작 [Run ID: {self.run_id}]")
        
        # 1. 상태 읽기
        state = self.get_last_sync_state()
        last_sync_time = state.get("last_sync_time")
        
        # 2. 파일 목록 조회
        try:
            # 수정: 재귀 함수 호출
            file_list = self.fetch_all_files_recursive(Config.DRIVE_ROOT_ID, last_sync_time)
            
            self.stats["total_found"] = len(file_list)
            logger.info(f"총 {len(file_list)}개의 변경/대상 파일 발견 (하위 폴더 포함)")
        except Exception as e:
            self.stats["error"] = str(e)
            self.finalize_run()
            return

        # 3. 동기화 루프
        max_modified_time = last_sync_time or "1970-01-01T00:00:00Z"
        
        for f in file_list:
            file_id = f.get('id')
            name = f.get('name')
            mime_type = f.get('mimeType')
            modified_time = f.get('modifiedTime')
            is_trashed = f.get('trashed', False)
            
            # 폴더는 스킵 (필요하다면 로직 추가)
            if mime_type == 'application/vnd.google-apps.folder':
                continue
                
            doc_id = generate_doc_id(Config.TENANT_ID, Config.ENGAGEMENT_ID, file_id)
            
            try:
                # 최신 modified_time 추적
                if modified_time > max_modified_time:
                    max_modified_time = modified_time

                logger.info(f"처리 중: {name} ({file_id}) [Trashed: {is_trashed}]")
                
                # Firestore 문서 기록용 메타데이터
                doc_meta = {
                    "tenant_id": Config.TENANT_ID,
                    "engagement_id": Config.ENGAGEMENT_ID,
                    "drive_file_id": file_id,
                    "doc_id": doc_id,
                    "filename": name,
                    "mime_type": mime_type,
                    "drive_modified_time": modified_time,
                    "last_synced_at": get_current_timestamp_iso(),
                    "active": not is_trashed, # Trashed이면 active=False
                    "sync_run_id": self.run_id
                }

                if is_trashed:
                    # Tombstone 처리
                    self.mark_as_deleted(doc_id, doc_meta)
                    self.stats["deleted"] += 1
                else:
                    # 다운로드 및 업로드
                    gcs_uri = self.process_file_upload(f, doc_id)
                    doc_meta["gcs_uri"] = gcs_uri
                    self.update_firestore_doc(doc_id, doc_meta)
                    self.stats["synced"] += 1

                self.sync_results.append({"doc_id": doc_id, "status": "success", "file_name": name})

            except Exception as e:
                logger.error(f"파일 처리 실패 ({name}): {e}")
                logger.debug(traceback.format_exc())
                self.stats["failed"] += 1
                self.sync_results.append({"doc_id": doc_id, "status": "failed", "error": str(e), "file_name": name})
        
        # 4. 상태 저장
        if self.stats["synced"] > 0 or self.stats["deleted"] > 0:
            self.save_sync_state(max_modified_time)
        else:
            logger.info("변경 사항 없음. 상태 업데이트 생략.")

        self.finalize_run()

    def process_file_upload(self, drive_file, doc_id):
        """파일 다운로드 후 GCS 업로드"""
        file_id = drive_file.get('id')
        filename = drive_file.get('name')
        
        # GCS 경로 생성
        # gs://{bucket}/{prefix}/{tenant_id}/{engagement_id}/raw/{doc_id}/{drive_file_id}/{filename}
        blob_path = f"{Config.GCS_PREFIX}/{Config.TENANT_ID}/{Config.ENGAGEMENT_ID}/raw/{doc_id}/{file_id}/{filename}"
        blob = self.bucket.blob(blob_path)

        # 구글 드라이브 파일 스트림 다운로드
        request = self.drive_service.files().get_media(fileId=file_id)
        
        # 메모리 버퍼 사용 (대용량 파일일 경우 임시 파일로 변경 고려)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            # logger.debug(f"Download {int(status.progress() * 100)}% ...")
        
        fh.seek(0)
        
        # GCS 업로드
        blob.upload_from_file(fh, rewind=True, content_type=drive_file.get('mimeType'))
        
        return f"gs://{Config.GCS_BUCKET}/{blob_path}"

    def mark_as_deleted(self, doc_id, meta):
        """Firestore에 active=False 기록"""
        doc_ref = self.db.collection("documents").document(doc_id)
        doc_ref.set(meta, merge=True)
        logger.info(f"문서 삭제 처리(Tombstone): {doc_id}")

    def update_firestore_doc(self, doc_id, meta):
        """Firestore에 문서 메타데이터 기록"""
        doc_ref = self.db.collection("documents").document(doc_id)
        doc_ref.set(meta, merge=True)
        logger.info(f"문서 메타데이터 업데이트: {doc_id}")

    def finalize_run(self):
        """실행 결과 저장 및 종료"""
        self.stats["end_time"] = get_current_timestamp_iso()
        
        # Result 저장
        run_data = {
            "run_id": self.run_id,
            "tenant_id": Config.TENANT_ID,
            "engagement_id": Config.ENGAGEMENT_ID,
            "stats": self.stats,
            # 상세 결과는 너무 많으면 별도 파일로 뺄 수 있음. 여기선 Array로 저장.
            "details": self.sync_results[:500] # 최대 500개만 저장 (Firestore 용량 고려)
        }
        self.run_ref.set(run_data)
        
        logger.info("동기화 완료")
        logger.info(f"Stat: {json.dumps(self.stats, indent=2)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant_id", help="Tenant ID Override")
    parser.add_argument("--engagement_id", help="Engagement ID Override")
    parser.add_argument("--doc_id", help="Doc ID (Ignored in full sync for now)")
    
    args, _ = parser.parse_known_args()
    
    # CLI 인자가 있으면 환경변수 오버라이딩 (Config가 os.getenv를 쓰므로)
    if args.tenant_id:
        os.environ["TENANT_ID"] = args.tenant_id
        Config.TENANT_ID = args.tenant_id # Explicit Override
    if args.engagement_id:
        os.environ["ENGAGEMENT_ID"] = args.engagement_id
        Config.ENGAGEMENT_ID = args.engagement_id # Explicit Override
        
    agent = DriveSyncAgent()
    agent.run()
