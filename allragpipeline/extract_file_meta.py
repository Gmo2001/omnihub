import os
import logging
import hashlib
import mimetypes
from typing import Optional, Dict, Any
from google.cloud import storage
from google.cloud import firestore
from dotenv import load_dotenv

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.PROJECT_ID: missing.append("GCP_PROJECT_ID")
        if not cls.GCS_BUCKET: missing.append("GCS_BUCKET")
        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")

# --- Logger Setup ---
def setup_logger():
    logger = logging.getLogger("FileMetaExtractor")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---

class FileMetaExtractor:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket_name = Config.GCS_BUCKET
        self.bucket = self.storage.bucket(self.bucket_name)

    def get_doctype_hint(self, content_type: Optional[str], filename: Optional[str]) -> str:
        """MIME Type 및 확장자 기반 문서 타입 힌트 생성"""
        
        # 1. MIME Type 우선 확인
        if content_type:
            if 'pdf' in content_type: return 'pdf'
            if 'image' in content_type: return 'image'
            if 'spreadsheet' in content_type or 'excel' in content_type: return 'xlsx'
            if 'presentation' in content_type or 'powerpoint' in content_type: return 'pptx'
            if 'wordprocessing' in content_type or 'msword' in content_type: return 'docx'
            if 'text/plain' in content_type: return 'txt'
            if 'json' in content_type: return 'json'
            if 'csv' in content_type: return 'csv'

        # 2. 확장자 확인 fallback
        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.pdf']: return 'pdf'
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']: return 'image'
            if ext in ['.xlsx', '.xls', '.csv']: return 'xlsx'
            if ext in ['.pptx', '.ppt']: return 'pptx'
            if ext in ['.docx', '.doc']: return 'docx'
            if ext in ['.txt', '.md', '.log']: return 'txt'

        return 'unknown'

    def generate_content_hash(self, blob: storage.Blob) -> str:
        """GCS 메타데이터를 기반으로 Content Hash 생성"""
        # 1. MD5 Hash 사용 (가장 선호)
        if blob.md5_hash:
            return blob.md5_hash
        
        # 2. 멀티파트 업로드 등으로 MD5가 없으면 조합 해시 생성
        # size + updated + crc32c
        raw_str = f"{blob.size}-{blob.updated}-{blob.crc32c}"
        return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

    def process_document(self, doc_snapshot):
        """단일 문서에 대한 메타 추출 처리"""
        doc_data = doc_snapshot.to_dict()
        doc_id = doc_snapshot.id
        
        # 필수 필드 확인
        gcs_uri = doc_data.get("gcs_uri")
        if not gcs_uri:
            logger.warning(f"SKIP: gcs_uri가 없음 - {doc_id}")
            return

        # GCS URI에서 Blob Path 추출 (gs://bucket_name/path...)
        if not gcs_uri.startswith(f"gs://{self.bucket_name}/"):
            logger.warning(f"SKIP: 버킷 불일치 또는 잘못된 URI - {gcs_uri}")
            return
        
        blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
        
        try:
            blob = self.bucket.blob(blob_path)
            blob.reload() # 메타데이터 불러오기
            
            # 메타데이터 추출
            content_type = blob.content_type
            filename = doc_data.get("filename") # Firestore 문서 정보 활용
            
            file_meta = {
                "doc_id": doc_id,
                "gcs_uri": gcs_uri,
                "size": blob.size,
                "content_type": content_type,
                "crc32c": blob.crc32c,
                "md5_hash": blob.md5_hash,
                "gcs_updated": blob.updated,
                "doc_content_hash": self.generate_content_hash(blob),
                "doctype_hint": self.get_doctype_hint(content_type, filename),
                "processed_at": firestore.SERVER_TIMESTAMP,
                "active": True
            }

            # Firestore 저장
            self.db.collection("file_metas").document(doc_id).set(file_meta, merge=True)
            logger.info(f"SUCCESS: {doc_id} ({file_meta['doctype_hint']})")
            
        except Exception as e:
            logger.error(f"FAIL: {doc_id} 처리 중 오류 - {e}")
            self.report_failure(doc_id, str(e))

    def report_failure(self, doc_id: str, error_msg: str):
        """실패 기록"""
        self.db.collection("file_metas").document(doc_id).set({
            "process_error": error_msg,
            "processed_at": firestore.SERVER_TIMESTAMP,
            "active": False # 메타 추출 실패 시 일단 비활성 처리 고려
        }, merge=True)

    def run_batch(self):
        """Firestore Documents 컬렉션을 순회하며 처리"""
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return

        logger.info("파일 메타 추출 작업 시작...")
        
        # active=True인 문서만 가져오기 (Tombstone 제외)
        docs_ref = self.db.collection("documents").where(filter=firestore.FieldFilter("active", "==", True))
        
        # 스트리밍 조회
        count = 0
        for doc in docs_ref.stream():
            self.process_document(doc)
            count += 1
            
        logger.info(f"작업 완료. 총 처리 문서 수: {count}")

if __name__ == "__main__":
    extractor = FileMetaExtractor()
    extractor.run_batch()
