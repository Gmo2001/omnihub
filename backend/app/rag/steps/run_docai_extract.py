import json
import time
import re
import logging
from typing import Optional, Dict, Any, List

from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.cloud import storage
from google.cloud import firestore

# [통합] 기존 프로젝트 설정 및 DB 가져오기
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# 로거 설정
logger = logging.getLogger("DocAIService")
logger.setLevel(logging.INFO)

class DocAIExtractor:
    def __init__(self):
        # [통합] 기존 전역 DB 클라이언트(db) 사용
        self.db = get_firestore_client()
        
        # GCS 설정 (Project ID 명시)
        self.project_id = settings.PROJECT_ID
        self.location = settings.DOC_AI_LOCATION
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        
        # GCS 클라이언트 - ADC 사용 (Cloud Run 호환)
        # 로컬에서는 GOOGLE_APPLICATION_CREDENTIALS 환경변수가 자동으로 사용됨
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket = self.storage_client.bucket(self.bucket_name)
        
        # Document AI Client - ADC 사용
        # Cloud Run에서는 서비스 계정 권한이 자동 부여됨
        opts = ClientOptions(api_endpoint=f"{self.location}-documentai.googleapis.com")
        self.docai_client = documentai.DocumentProcessorServiceClient(
            client_options=opts
        )

    def get_processor_name(self, mime_type: str) -> Optional[str]:
        """MIME Type에 따른 Processor ID 결정 (.env 설정 필요)"""
        # settings에 해당 필드가 없다면 기본값이나 fallback 사용
        proc_pdf = getattr(settings, "DOC_AI_PROCESSOR_ID_PDF", settings.DOCAI_PROCESSOR_ID)
        proc_img = getattr(settings, "DOC_AI_PROCESSOR_ID_IMAGE", settings.DOCAI_PROCESSOR_ID)
        
        processor_id = None
        if 'pdf' in mime_type:
            processor_id = proc_pdf
        elif 'image' in mime_type:
            processor_id = proc_img or proc_pdf
        
        if not processor_id:
            logger.warning(f"지원하지 않는 MIME Type: {mime_type}")
            return None
            
        return self.docai_client.processor_path(self.project_id, self.location, processor_id)

    def process_single_document(self, file_id: str, gcs_uri: str, mime_type: str):
        """
        단일 문서에 대해 OCR(Batch Process)을 수행합니다.
        (Ingestion Service의 BackgroundTask에서 호출됨)
        """
        logger.info(f"🚀 [DocAI] 처리 시작: {file_id} ({mime_type})")

        processor_name = self.get_processor_name(mime_type)
        if not processor_name:
            return

        try:
            # 1. Output 경로 설정 (덮어쓰기 방지용 타임스탬프)
            # 구조: docai_output/{file_id}/{timestamp}/
            timestamp = int(time.time())
            output_prefix = f"docai_output/{file_id}/{timestamp}"
            output_gcs_uri = f"gs://{self.bucket_name}/{output_prefix}"

            # 2. Batch Process Request 구성
            input_config = documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(
                    documents=[
                        documentai.GcsDocument(
                            gcs_uri=gcs_uri,
                            mime_type=mime_type
                        )
                    ]
                )
            )
            
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

            # 3. LRO 실행 (Blocking)
            # 주의: 이 함수는 BackgroundTasks 안에서 실행되어야 메인 서버를 멈추지 않음
            logger.info(f" -> Google Cloud에 분석 요청 중... (File: {file_id})")
            operation = self.docai_client.batch_process_documents(request=request)
            
            # 대기 (최대 10분)
            operation.result(timeout=600) 
            logger.info(f" -> 분석 완료. 결과 수집 중...")

            # 4. 결과 파일들(JSON) 읽기 및 병합
            merged_artifact = self.fetch_and_merge_results(output_prefix)
            
            # 5. 최종 결과 DB 저장 (docai_results 컬렉션)
            # [통합] 기존 시스템의 컬렉션 명명 규칙 따름
            page_count = len(merged_artifact.get("pages", []))
            
            result_doc = {
                "doc_id": file_id,
                "file_id": file_id, # 참조용
                "full_text": merged_artifact.get("full_text"),
                "pages": merged_artifact.get("pages"),
                "status": "completed",
                "processed_at": firestore.SERVER_TIMESTAMP,
                "raw_output_uri": output_gcs_uri,
                "page_count": page_count,
                "processor_used": processor_name
            }
            
            self.db.collection("docai_results").document(file_id).set(result_doc, merge=True)
            
            # 원본 파일 상태 업데이트
            self.db.collection("files").document(file_id).set({
                "aiStatus": "completed",
                "pageCount": page_count
            }, merge=True)
            
            logger.info(f"✅ [DocAI] 최종 완료: {file_id} (페이지: {page_count})")

            # [Pipeline] Orchestrator manages the next steps.
            # No manual trigger here.
            pass

        except Exception as e:
            logger.error(f"❌ [DocAI] 실패 ({file_id}): {e}")
            self.db.collection("files").document(file_id).update({
                "aiStatus": "failed", 
                "errorMsg": str(e)
            })

    def fetch_and_merge_results(self, output_prefix: str) -> Dict[str, Any]:
        """GCS 분할 JSON 병합 (제공해주신 로직 유지)"""
        blobs = list(self.bucket.list_blobs(prefix=output_prefix))
        json_blobs = [b for b in blobs if b.name.endswith(".json")]
        json_blobs.sort(key=lambda x: x.name)

        all_pages = []
        full_text_builder = ""
        
        for blob in json_blobs:
            content = blob.download_as_bytes()
            shard_dict = json.loads(content)
            
            shard_text = shard_dict.get("text", "")
            full_text_builder += shard_text
            
            parsed = self.parse_shard_result(shard_dict)
            all_pages.extend(parsed['pages'])
        
        all_pages.sort(key=lambda p: p['page_no'])

        return {
            "full_text": full_text_builder,
            "pages": all_pages
        }

    def parse_shard_result(self, shard_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Shard 파싱 (제공해주신 로직 유지)"""
        full_text = shard_dict.get("text", "")
        pages = []
        source_pages = shard_dict.get("pages", [])
        
        for page in source_pages:
            page_no = page.get("pageNumber", 1)
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

# main 함수 추가
if __name__ == "__main__":
    extractor = DocAIExtractor()
    extractor.process_single_document("test_file_id", "gs://test_bucket/test_file.pdf", "application/pdf")