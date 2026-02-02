import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from google.cloud import firestore
from google.cloud import storage

# vertexai 모듈 (조건부 import 가능하나 여기선 필수 가정)
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# 로컬 환경 변수 로드
load_dotenv()

if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "vertex").lower()
    VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
    VERTEX_MODEL = os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-exp")
    
    PROMPT_VERSION = os.getenv("SUMMARY_PROMPT_VERSION", "v1")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.GCS_BUCKET: raise ValueError("GCS_BUCKET 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("CardSummarizer")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- LLM Client Wrapper ---
class LLMClient:
    def __init__(self):
        if Config.LLM_PROVIDER == 'vertex':
            vertexai.init(project=Config.PROJECT_ID, location=Config.VERTEX_LOCATION)
            self.model = GenerativeModel(Config.VERTEX_MODEL)
        else:
            raise NotImplementedError(f"Provider {Config.LLM_PROVIDER} not implemented yet.")

    def generate_card_summary(self, text_context: str) -> Dict[str, str]:
        """LLM을 호출하여 3줄 요약 생성 (JSON 리턴 기대)"""
        
        prompt = f"""
You are an expert document summarizer.
Based on the provided document text, create a structured 3-level summary for a preview card.

Input Text:
{text_context[:30000]} 

Requirements:
- Output must be valid JSON with keys: "l1", "l2", "l3".
- l1: Main Topic or Title (Max 20 chars).
- l2: Key Message or Conclusion (Max 50 chars).
- l3: Detailed Summary or Context (Max 100 chars).
- Language: Korean (한국어).
- Do not include markdown code blocks (```json). Just raw JSON.

Output JSON:
"""
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            # Markdown 제거
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json\n", "").replace("json", "")
            
            return json.loads(raw_text)
            
        except Exception as e:
            logger.error(f"LLM Generation Failed: {e}")
            return {"l1": "요약 실패", "l2": "LLM 호출 오류", "l3": str(e)[:50]}

# --- Core Logic ---
class CardSummarizer:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        self.llm = LLMClient()

    def load_chunks(self, chunks_uri: str) -> List[Dict[str, Any]]:
        if not chunks_uri or not chunks_uri.startswith("gs://"):
            return []
        
        blob_path = chunks_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        content = blob.download_as_text()
        return json.loads(content)

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile = doc_snapshot.to_dict()
        
        # Flag Check
        flags = profile.get("process_flags", {})
        if flags.get("card") is False:
             return

        logger.info(f"Summarizing {doc_id}...")

        # 1. Chunk 로드
        # chunks 컬렉션에서 GCS URI 조회
        chunk_ref = self.db.collection("chunks").document(doc_id).get()
        if not chunk_ref.exists:
            logger.warning(f"SKIP {doc_id}: Chunks not found")
            return
            
        chunks_uri = chunk_ref.get("gcs_chunks_uri")
        chunks = self.load_chunks(chunks_uri)
        
        if not chunks:
            logger.warning(f"SKIP {doc_id}: Empty chunks")
            return

        # 2. Context 구성 (앞부분 5개 청크 정도 사용)
        input_chunks = chunks[:5] 
        context_text = "\n\n".join([c.get("text", "") for c in input_chunks])
        
        # 3. LLM 요약
        summary_json = self.llm.generate_card_summary(context_text)
        
        # 4. 저장 데이터 구성
        source_link = profile.get("source_link")
        
        # Evidence Schema Conforming
        evidence_list = []
        for c in input_chunks:
            evidence_list.append({
                "doc_id": doc_id,
                "chunk_id": c.get("chunk_id"),
                "page": c.get("page_start_no"),
                "source_link": source_link,
                "snippet": c.get("text", "")[:300],
                "span": None
            })

        card_data = {
            "doc_id": doc_id,
            "tenant_id": Config.TENANT_ID,
            "engagement_id": Config.ENGAGEMENT_ID,
            "card": summary_json,
            "card_evidence": evidence_list,
            "redaction_applied": False, # 여기선 기능 생략 (False 고정)
            "summary_prompt_version": Config.PROMPT_VERSION,
            "model_version": Config.VERTEX_MODEL,
            "generated_at": firestore.SERVER_TIMESTAMP
        }
        
        batch = self.db.batch()
        
        # cards/{doc_id}
        batch.set(self.db.collection("cards").document(doc_id), card_data, merge=True)
        
        # documents/{doc_id} (Mirroring)
        batch.set(self.db.collection("documents").document(doc_id), {
            "card_summary": summary_json,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # profiles/{doc_id} (Flag Off)
        batch.set(self.db.collection("profiles").document(doc_id), {
            "process_flags": {"card": False}
        }, merge=True)
        
        batch.commit()
        logger.info(f"SUCCESS {doc_id}: {summary_json.get('l1')}")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Card Summary 작업 시작...")
        
        docs = self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).stream()
        
        count = 0
        for doc in docs:
            try:
                self.process_document(doc)
                count += 1
            except Exception as e:
                logger.error(f"FAIL {doc.id}: {e}")
                
        logger.info(f"작업 완료. 총 {count}개 문서 처리.")

if __name__ == "__main__":
    summarizer = CardSummarizer()
    summarizer.run_batch()
