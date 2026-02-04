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
    PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID")
    
    # [Flexible Config] Support both DOCAI_ (User Pref) and DOC_AI_ (Standard)
    LOCATION = os.getenv("DOCAI_LOCATION") or os.getenv("DOC_AI_LOCATION", "us")
    
    # If user provided a single generic ID (DOCAI_PROCESSOR_ID), use it for both.
    _GENERIC_PROCESSOR_ID = os.getenv("DOCAI_PROCESSOR_ID")
    
    PROCESSOR_ID_PDF = os.getenv("DOC_AI_PROCESSOR_ID_PDF") or _GENERIC_PROCESSOR_ID
    PROCESSOR_ID_IMAGE = os.getenv("DOC_AI_PROCESSOR_ID_IMAGE") or _GENERIC_PROCESSOR_ID
    
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
        # Ensure at least one processor ID is available if we are to fallback
        if not cls.PROCESSOR_ID_PDF and not cls.PROCESSOR_ID_IMAGE: 
             missing.append("DOCAI_PROCESSOR_ID (or PDF/IMAGE variant)")
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
        
        # [files Schema Adaptation]
        content_type = data.get("mimeType", "")
        gcs_uri = data.get("gcsUri")
        # Reuse driveModifiedTime or similar as hash equivalent check?
        # For simplicity, we just use fileId + driveModifiedTime
        current_hash = f"{doc_id}_{data.get('driveModifiedTime', '')}"
        
        if not gcs_uri:
            logger.warning(f"SKIP {doc_id}: GCS URI 누락")
            return

        # Check existing result in ai_results (Root Status)
        # We can perform a quick check if "ocr=success" exists in status_summary
        root_ref = self.db.collection("ai_results").document(doc_id)
        root_snap = root_ref.get()
        if root_snap.exists:
             status_summary = root_snap.to_dict().get("status_summary", {})
             if status_summary.get("ocr") == "success":
                 # Potentially skip if not modified. For now force run.
                 pass

        processor_name = self.get_processor_name(content_type)
        if not processor_name:
            logger.info(f"SKIP {doc_id}: 지원하지 않는 Content-Type ({content_type})")
            return
            
        logger.info(f"Processing Async {doc_id} ({content_type})...")

        try:
            # 1. Output Path
            output_prefix = f"docai/{doc_id}/{current_hash}/raw_output"
            output_gcs_uri = f"gs://{Config.GCS_BUCKET}/{output_prefix}"

            # 2. Batch Process Input
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
            
            # Output
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

            # 3. Exec & Wait
            logger.info(f" -> Batch Operation 시작... (Input: {gcs_uri})")
            operation = self.docai_client.batch_process_documents(request=request)
            operation.result(timeout=600) 
            logger.info(f" -> Batch Operation 완료. 결과 수집 중...")

            # 4. Merge Results
            merged_artifact = self.fetch_and_merge_results(output_prefix)
            
            # 5. Extract Keywords for Indexing (Simple Tokenizer)
            full_text = merged_artifact.get("full_text", "")
            # Simple alphanumeric extraction
            tokens = set(re.findall(r'\w+', full_text.lower()))
            # Limit tokens to avoid explosion (e.g. len > 2)
            valid_tokens = [t for t in tokens if len(t) > 2][:500] 

            batch = self.db.batch()

            # 6. Save to 'ai_results' (Sub-collection Strategy)
            
            # 6.1 Root Document (Status & Metadata)
            batch.set(root_ref, {
                "doc_id": doc_id,
                "last_processed_at": firestore.SERVER_TIMESTAMP,
                "status_summary": {"ocr": "success"}, # Merged into map
                "keywords": list(valid_tokens)[:50] # For simple filter
            }, merge=True)
            
            # 6.2 Sub-collection: OCR Output
            ocr_output_ref = root_ref.collection("ocr_outputs").document("latest")
            batch.set(ocr_output_ref, {
                "doc_id": doc_id,
                "doc_content_hash": current_hash,
                "raw_output_uri": output_gcs_uri,
                "full_text": full_text, 
                "pages": merged_artifact.get("pages", []),
                "page_count": len(merged_artifact.get("pages", [])),
                "processed_at": firestore.SERVER_TIMESTAMP,
                "processor_used": processor_name,
                "type": "ocr_output"
            })
            
            # 6.3 Update Inverted Index (ai_indices)
            for token in valid_tokens:
                token_ref = self.db.collection("ai_indices").document(token)
                batch.set(token_ref, {
                    "files": firestore.ArrayUnion([doc_id]),
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True)
                
            batch.commit()
            
            logger.info(f"SUCCESS {doc_id}: OCR Saved (Sub-collection), Indices Updated")

        except Exception as e:
            logger.error(f"FAIL {doc_id}: {e}")
            # Update 'files' status to failed? (Typically handled by Runner/Analysis Service)
            pass

    def run(self, doc_id: str = None, tenant_id: str = None, engagement_id: str = None):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return

        if doc_id:
            logger.info(f"DocAI Extract 단일 실행: {doc_id}")
            # [Direct Access] fetch 'files/{doc_id}'
            doc_snap = self.db.collection("files").document(doc_id).get()
            if doc_snap.exists:
                self.process_document(doc_snap)
            else:
                logger.error(f"Doc ID {doc_id} not found in files.")
            return

        logger.info("DocAI Extract Helper (Async Batch) 시작...")
        
        # [Direct Access] 'files' collection
        col_ref = self.db.collection("files")
        docs = []

        try:
            if tenant_id: 
                # Engagement is optional in files schema?
                logger.info(f"Target Scope: {tenant_id}")
                query = col_ref.where(filter=firestore.FieldFilter("fileDeptId", "==", tenant_id))
                docs = list(query.get(timeout=600))
                
            else:
                # Just get all non-trashed files?
                logger.info("Target All Active Files")
                query = col_ref.where(filter=firestore.FieldFilter("trashed", "==", False))
                docs = list(query.get(timeout=600)) # Limit might be needed

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
    extractor.run(doc_id=args.doc_id, tenant_id=args.tenant_id, engagement_id=args.engagement_id)
