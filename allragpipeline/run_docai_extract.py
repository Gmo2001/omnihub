import os
import json
import logging
import time
import re
import argparse
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.cloud import storage
from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("DOC_AI_LOCATION", "us")
    PROCESSOR_ID_PDF = os.getenv("DOC_AI_PROCESSOR_ID_PDF")
    PROCESSOR_ID_IMAGE = os.getenv("DOC_AI_PROCESSOR_ID_IMAGE")
    
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    GCS_PREFIX = os.getenv("GCS_PREFIX", "omnihub")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.PROJECT_ID: missing.append("GCP_PROJECT_ID")
        if not cls.PROCESSOR_ID_PDF: missing.append("DOC_AI_PROCESSOR_ID_PDF")
        if not cls.GCS_BUCKET: missing.append("GCS_BUCKET")
        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("DocAIExtractorAsync")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---

class DocAIExtractor:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        
        # Document AI Client Setting
        opts = ClientOptions(api_endpoint=f"{Config.LOCATION}-documentai.googleapis.com")
        self.docai_client = documentai.DocumentProcessorServiceClient(client_options=opts)

    def get_processor_name(self, mime_type: str) -> Optional[str]:
        """MIME Type에 따른 Processor ID 결정"""
        processor_id = None
        
        if 'pdf' in mime_type:
            processor_id = Config.PROCESSOR_ID_PDF
        elif 'image' in mime_type:
            processor_id = Config.PROCESSOR_ID_IMAGE or Config.PROCESSOR_ID_PDF
        
        if not processor_id:
            return None
            
        return self.docai_client.processor_path(Config.PROJECT_ID, Config.LOCATION, processor_id)

    def process_document(self, file_meta_doc):
        data = file_meta_doc.to_dict()
        doc_id = file_meta_doc.id
        
        content_type = data.get("content_type", "")
        gcs_uri = data.get("gcs_uri")
        current_hash = data.get("doc_content_hash")
        
        # 유효성 검사
        if not gcs_uri or not current_hash:
            logger.warning(f"SKIP {doc_id}: 필수 메타데이터 누락")
            return

        # Idempotency
        artifact_ref = self.db.collection("docai_artifacts").document(doc_id).get()
        if artifact_ref.exists:
            existing_data = artifact_ref.to_dict()
            if existing_data.get("doc_content_hash") == current_hash:
                logger.info(f"SKIP {doc_id}: 이미 최신 버전이 처리됨")
                return

        processor_name = self.get_processor_name(content_type)
        if not processor_name:
            logger.info(f"SKIP {doc_id}: 지원하지 않는 Content-Type ({content_type})")
            return
            
        logger.info(f"Processing Async {doc_id} ({content_type})...")

        try:
            # 1. Output 경로 설정
            # GCS Output Prefix: docai/{doc_id}/{hash}/raw_output
            output_prefix = f"docai/{doc_id}/{current_hash}/raw_output"
            output_gcs_uri = f"gs://{Config.GCS_BUCKET}/{output_prefix}"

            # 2. Batch Process Request 구성
            # 입력 설정
            input_config = documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(
                    documents=[
                        documentai.GcsDocument(
                            gcs_uri=gcs_uri,
                            mime_type=content_type
                        )
                    ]
                )
            )
            
            # 출력 설정
            output_config = documentai.DocumentOutputConfig(
                gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                    gcs_uri=output_gcs_uri
                )
            )

            request = documentai.BatchProcessRequest(
                name=processor_name,
                input_documents=input_config,
                document_output_config=output_config,
            )

            # 3. LRO 실행 및 대기
            logger.info(f" -> Batch Operation 시작... (Input: {gcs_uri})")
            operation = self.docai_client.batch_process_documents(request=request)
            
            # 대기 (타임아웃 설정 가능, 여기선 기본 300초 이상 걸릴 수 있으니 넉넉히)
            # 대용량 파일은 오래 걸리므로 로그를 주기적으로 찍는 polling 방식이 좋지만, 
            # 간단히 result()로 blocking.
            operation.result(timeout=600) 
            
            logger.info(f" -> Batch Operation 완료. 결과 수집 중...")

            # 4. 결과 파일들(JSON) 읽기 및 병합
            merged_artifact = self.fetch_and_merge_results(output_prefix)
            
            # 5. 최종 산출물 저장 (우리가 원하는 구조로 정리된 JSON)
            # gs://{bucket}/docai/{doc_id}/{hash}/artifact.json
            final_artifact_path = f"docai/{doc_id}/{current_hash}/artifact.json"
            final_blob = self.bucket.blob(final_artifact_path)
            
            final_blob.upload_from_string(
                json.dumps(merged_artifact, ensure_ascii=False),
                content_type="application/json"
            )
            final_artifact_uri = f"gs://{Config.GCS_BUCKET}/{final_artifact_path}"
            
            # 6. Firestore 업데이트
            page_count = len(merged_artifact.get("pages", []))
            self.db.collection("docai_artifacts").document(doc_id).set({
                "doc_id": doc_id,
                "doc_content_hash": current_hash,
                "gcs_artifact_uri": final_artifact_uri,
                "raw_output_uri": output_gcs_uri, # 원본 DocAI 출력 위치도 기록
                "page_count": page_count,
                "processed_at": firestore.SERVER_TIMESTAMP,
                "processor_used": processor_name,
                "method": "batch_async"
            }, merge=True)
            
            logger.info(f"SUCCESS {doc_id}: Page Count {page_count}")

            # (선택) raw_output 폴더 정리?
            # 디버깅을 위해 남겨두는 편이 좋음.

        except Exception as e:
            logger.error(f"FAIL {doc_id}: {e}")
            self.db.collection("docai_artifacts").document(doc_id).set({
                "process_error": str(e),
                "last_attempt": firestore.SERVER_TIMESTAMP
            }, merge=True)

    def fetch_and_merge_results(self, output_prefix: str) -> Dict[str, Any]:
        """GCS에 저장된 DocAI 분할 JSON 파일들을 찾아 읽고 하나로 병합"""
        
        blobs = list(self.bucket.list_blobs(prefix=output_prefix))
        
        # 메타데이터 및 샤딩된 파일 필터링
        json_blobs = [b for b in blobs if b.name.endswith(".json")]
        
        # 정렬 (보통 output-page-1-to-X.json 형식이므로 이름순 정렬)
        # 하지만 DocAI는 랜덤한 폴더 구조를 만들기도 함: prefix/random_id/0/output...
        # 따라서 모든 JSON을 읽어서 page number 기준으로 재정렬하는 것이 안전함.
        
        all_pages = []
        full_text_parts = [] # 전체 텍스트 병합용 (단, DocAI의 text 필드는 전체가 아닐 수 있음 - Shard면 부분일 수 있음)
        
        # DocAI의 Sharded Document는 `text` 필드가 각 Shard에 포함된 부분 텍스트일 수도 있고,
        # 전체 텍스트가 첫 번째 Shard에만 있을 수도 있음.
        # 일반적으로 Batch Process Output은 각 Shard가 독립적인 Document 객체처럼 보이지만
        # text는 해당 페이지 범위에 대한 것일 가능성이 높음.
        
        # 간단 병합 전략:
        # 각 JSON을 documentai.Document 객체로 파싱 -> pages 추출 -> 병합
        
        # 참고: Sharded output의 text 필드는 해당 shard의 text임.
        # 전체 full_text를 재구성하려면 각 shard의 text를 이어붙여야 함.
        
        json_blobs.sort(key=lambda x: x.name) # 파일명 순 정렬 (보통 순서대로 생성됨)

        full_text_builder = ""
        
        for blob in json_blobs:
            content = blob.download_as_bytes()
            # Document 객체로 로드 (protobuf -> json)
            # 여기선 json.loads로 Dict로 처리
            shard_dict = json.loads(content)
            
            # Text 병합
            shard_text = shard_dict.get("text", "")
            full_text_builder += shard_text
            
            # 파싱 (개별 Shard에 대해)
            # 주의: Shard된 문서의 Page 인덱스가 1부터 시작하는지, 전체 기준인지 확인 필요.
            # Batch Output은 전체 문서 기준의 Page Number를 가짐.
            parsed = self.parse_shard_result(shard_dict)
            all_pages.extend(parsed['pages'])
        
        # 페이지 번호 순 정렬
        all_pages.sort(key=lambda p: p['page_no'])

        return {
            "full_text": full_text_builder,
            "pages": all_pages,
            # 테이블 병합은 복잡하므로 여기선 생략하거나 pages 안에 포함
            "tables": [] # 필요 시 구현
        }

    def parse_shard_result(self, shard_dict: Dict[str, Any]) -> Dict[str, Any]:
        """단일 Shard JSON 파싱"""
        full_text = shard_dict.get("text", "")
        pages = []
        
        source_pages = shard_dict.get("pages", [])
        for page in source_pages:
            page_no = page.get("pageNumber", 1) # 1-based index
            
            # 텍스트 추출 (Layout Segment 활용)
            segments_text = []
            layout = page.get("layout", {})
            text_anchor = layout.get("textAnchor", {})
            text_segments = text_anchor.get("textSegments", [])
            
            for segment in text_segments:
                start = int(segment.get("startIndex", "0"))
                end = int(segment.get("endIndex", "0"))
                if end > start:
                    segments_text.append(full_text[start:end])
            
            pages.append({
                "page_no": page_no,
                "text": "".join(segments_text),
                "width": page.get("dimension", {}).get("width"),
                "height": page.get("dimension", {}).get("height")
            })
            
        return {"pages": pages}

    def run_batch(self, doc_id: str = None, tenant_id: str = None, engagement_id: str = None):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return

        logger.info("DocAI Extract Helper (Async Batch) 시작...")
        
        # Query Setup
        col_ref = self.db.collection("file_metas")
        docs = []

        try:
            if doc_id:
                # 단일 문서 모드
                logger.info(f"Target Single Doc: {doc_id}")
                doc_snap = col_ref.document(doc_id).get()
                if doc_snap.exists:
                    docs = [doc_snap]
                else:
                    logger.warning(f"Doc ID {doc_id} not found in file_metas.")
            
            elif tenant_id and engagement_id:
                # 테넌트/프로젝트 단위 실행
                logger.info(f"Target Scope: {tenant_id} / {engagement_id}")
                # 주의: index 필요할 수 있음. active=True 포함.
                query = (col_ref.where(filter=firestore.FieldFilter("tenant_id", "==", tenant_id))
                               .where(filter=firestore.FieldFilter("engagement_id", "==", engagement_id))
                               .where(filter=firestore.FieldFilter("active", "==", True)))
                
                # Stream 대신 List + Timeout 사용
                docs = list(query.get(timeout=600))
                
            else:
                # 전체 실행 (기존 로직)
                logger.info("Target All Active Docs")
                query = col_ref.where(filter=firestore.FieldFilter("active", "==", True))
                docs = list(query.get(timeout=600))

        except Exception as e:
            logger.error(f"Firestore Query Failed: {e}")
            return

        logger.info(f"총 {len(docs)}건의 문서 메타데이터를 로드했습니다. 처리를 시작합니다.")
        
        count = 0
        for doc in docs:
            self.process_document(doc)
            count += 1
            
        logger.info(f"작업 완료. 총 {count}개 문서 확인.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc_id", help="Target Doc ID")
    parser.add_argument("--tenant_id", help="Tenant ID")
    parser.add_argument("--engagement_id", help="Engagement ID")
    args, _ = parser.parse_known_args()

    extractor = DocAIExtractor()
    extractor.run_batch(doc_id=args.doc_id, tenant_id=args.tenant_id, engagement_id=args.engagement_id)
