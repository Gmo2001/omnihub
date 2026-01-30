import os
import logging
import time
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from google.oauth2 import service_account
from google.auth import default
from googleapiclient.discovery import build
from google.cloud import firestore
from google.api_core import exceptions as google_exceptions

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    # Auth
    AUTH_MODE = os.getenv("DRIVE_OAUTH_MODE", "sa").lower()
    SA_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    IMPERSONATE_EMAIL = os.getenv("DRIVE_IMPERSONATE_EMAIL")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.PROJECT_ID: missing.append("GCP_PROJECT_ID")
        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("DriveMetaFetcher")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Services ---
def get_drive_service():
    scopes = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.metadata.readonly']
    
    if Config.AUTH_MODE == 'dwd':
        if not Config.SA_KEY_PATH or not Config.IMPERSONATE_EMAIL:
            raise ValueError("DWD 모드에는 SA Key와 Impersonate Email이 필요합니다.")
        creds = service_account.Credentials.from_service_account_file(Config.SA_KEY_PATH, scopes=scopes)
        creds = creds.with_subject(Config.IMPERSONATE_EMAIL)
    elif Config.AUTH_MODE == 'sa':
        if Config.SA_KEY_PATH:
            creds = service_account.Credentials.from_service_account_file(Config.SA_KEY_PATH, scopes=scopes)
        else:
            creds, _ = default()
    else:
        creds, _ = default()
        
    return build('drive', 'v3', credentials=creds)

# --- Core Logic ---

class DriveMetaFetcher:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.drive_service = get_drive_service()
        self.folder_cache = {} # id -> {name, parent_id}

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Drive API로 기본 메타데이터 조회"""
        try:
            fields = "id, name, mimeType, modifiedTime, owners(emailAddress, displayName), parents, webViewLink, trashed, capabilities(canShare)"
            return self.drive_service.files().get(fileId=file_id, fields=fields).execute()
        except Exception as e:
            logger.error(f"메타데이터 조회 실패 ({file_id}): {e}")
            raise

    def get_permissions_summary(self, file_id: str) -> Dict[str, Any]:
        """권한 목록 조회 및 요약"""
        summary = {
            "anyone_can_read": False,
            "domain_can_read": False,
            "external_users": [],
            "roles": []
        }
        try:
            # permissions.list는 파일 소유자가 아니거나 권한이 없으면 제한될 수 있음
            perms = self.drive_service.permissions().list(
                fileId=file_id, 
                fields="permissions(type, role, emailAddress, domain)"
            ).execute().get('permissions', [])
            
            roles = set()
            for p in perms:
                p_type = p.get('type')
                p_role = p.get('role')
                roles.add(p_role)
                
                if p_type == 'anyone':
                    summary["anyone_can_read"] = True
                elif p_type == 'domain':
                    summary["domain_can_read"] = True
                elif p_type == 'user':
                    email = p.get('emailAddress')
                    if email:
                        # 간단히 외부 도메인 판별 로직 (예시)
                        # 실제로는 조직 도메인 설정이 필요함
                        pass

            summary["roles"] = list(roles)
            return summary
        except Exception as e:
            logger.warning(f"권한 조회 실패 또는 권한 부족 ({file_id}): {e}")
            return {"error": str(e)}

    def resolve_folder_path(self, parents: List[str]) -> str:
        """재귀적으로 부모 폴더명을 찾아 경로 구성 (캐시 사용)"""
        if not parents:
            return "/"
            
        parent_id = parents[0] # 첫 번째 부모만 따라감
        path_segments = []
        
        current_id = parent_id
        depth = 0
        max_depth = 15  # 무한 루프 방지
        
        while current_id and depth < max_depth:
            # 캐시 확인
            if current_id in self.folder_cache:
                info = self.folder_cache[current_id]
                path_segments.insert(0, info['name'])
                current_id = info.get('parent_id')
            else:
                # 쿼리
                try:
                    folder = self.drive_service.files().get(
                        fileId=current_id, 
                        fields="id, name, parents"
                    ).execute()
                    
                    name = folder.get('name', 'Unknown')
                    folder_parents = folder.get('parents', [])
                    p_id = folder_parents[0] if folder_parents else None
                    
                    # 캐시 저장
                    self.folder_cache[current_id] = {'name': name, 'parent_id': p_id}
                    
                    path_segments.insert(0, name)
                    current_id = p_id
                except Exception as e:
                    logger.warning(f"폴더 경로 추적 실패 ({current_id}): {e}")
                    path_segments.insert(0, "?")
                    break
            
            depth += 1
            
        return "/" + "/".join(path_segments)

    def process_document(self, doc_snapshot):
        doc_data = doc_snapshot.to_dict()
        doc_id = doc_snapshot.id
        drive_file_id = doc_data.get("drive_file_id")

        if not drive_file_id:
            logger.warning(f"SKIP: drive_file_id 없음 ({doc_id})")
            return

        try:
            logger.info(f"Processing: {doc_id} (DriveID: {drive_file_id})")
            
            # 1. 파일 메타
            meta = self.get_file_metadata(drive_file_id)
            if meta.get('trashed'):
                logger.info(f"Trashed File: {drive_file_id}")
                # 필요시 active=False 처리 가능하나 여기선 메타만 저장
            
            # 2. 경로 재구성
            parents = meta.get('parents', [])
            folder_path = self.resolve_folder_path(parents)
            
            # 3. 권한 (옵션)
            perms = self.get_permissions_summary(drive_file_id)
            
            # 4. 저장 데이터 구성
            drive_meta = {
                "doc_id": doc_id,
                "drive_file_id": drive_file_id,
                "name": meta.get('name'),
                "mime_type": meta.get('mimeType'),
                "folder_path": folder_path,
                "owners": [o.get('emailAddress') for o in meta.get('owners', [])],
                "drive_modified_time": meta.get('modifiedTime'), # 원본 수정일
                "source_link": meta.get('webViewLink'),
                "permissions_summary": perms,
                "fetched_at": firestore.SERVER_TIMESTAMP
            }
            
            self.db.collection("drive_metas").document(doc_id).set(drive_meta, merge=True)
            logger.info(f"Saved drive_meta for {doc_id}")

        except Exception as e:
            logger.error(f"FAILED {doc_id}: {e}")
            self.db.collection("drive_metas").document(doc_id).set({
                "fetch_error": str(e),
                "fetched_at": firestore.SERVER_TIMESTAMP
            }, merge=True)

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return 

        logger.info("Drive Meta Fetch 시작...")
        
        # documents 컬렉션 순회 (active=True인 것만)
        docs = self.db.collection("documents").where(filter=firestore.FieldFilter("active", "==", True)).stream()
        
        count = 0
        for doc in docs:
            self.process_document(doc)
            count += 1
            
            # 너무 빠른 API 호출 방지 (Quota)
            if count % 10 == 0:
                time.sleep(1)

        logger.info(f"작업 완료. 총 {count}개 처리.")

if __name__ == "__main__":
    fetcher = DriveMetaFetcher()
    fetcher.run_batch()
