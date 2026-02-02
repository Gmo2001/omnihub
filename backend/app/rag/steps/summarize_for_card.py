import json
import logging
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("CardSummarizer")
logger.setLevel(logging.INFO)

class CardSummarizer:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.location = getattr(settings, "VERTEX_LOCATION", "us-central1")
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)

        # Vertex Init
        vertexai.init(project=self.project_id, location=self.location)
        model_name = getattr(settings, "VERTEX_MODEL_NAME", "gemini-2.0-flash-exp")
        self.model = GenerativeModel(model_name)

    def generate_card_summary(self, text_context: str):
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
        - Do not include markdown code blocks. Just raw JSON.
        """
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json\n", "").replace("json", "")
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"LLM Summary Fail: {e}")
            return {"l1": "요약 실패", "l2": "LLM 호출 오류", "l3": str(e)[:50]}

    def load_chunks(self, chunks_uri: str):
        if not chunks_uri.startswith("gs://"): return []
        blob_path = chunks_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            content = blob.download_as_text()
            return json.loads(content)
        except Exception:
            return []

    def process_single_document(self, doc_id: str):
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile = profile_ref.to_dict()
        if not profile.get("active"): return

        logger.info(f"📝 [Card] 요약 시작: {doc_id}")

        # Load chunks
        chunk_ref = self.db.collection("chunks").document(doc_id).get()
        if not chunk_ref.exists:
            logger.warning(f"SKIP Card: Chunks not found {doc_id}")
            return
        
        chunks = self.load_chunks(chunk_ref.get("gcs_chunks_uri"))
        if not chunks:
            logger.warning(f"SKIP Card: Empty chunks {doc_id}")
            return
            
        # Context building (Head 5 chunks)
        # Filter only text chunks
        text_chunks = [c for c in chunks if c.get("type", "text") == "text"]
        input_chunks = text_chunks[:5]
        context_text = "\n\n".join([c.get("text", "") for c in input_chunks])
        
        # LLM Call
        summary_json = self.generate_card_summary(context_text)
        
        # Evidence
        source_link = profile.get("source_link")
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
            "tenant_id": getattr(settings, "TENANT_ID", "default"),
            "engagement_id": getattr(settings, "ENGAGEMENT_ID", "default"),
            "card": summary_json,
            "card_evidence": evidence_list,
            "generated_at": firestore.SERVER_TIMESTAMP
        }
        
        batch = self.db.batch()
        batch.set(self.db.collection("cards").document(doc_id), card_data, merge=True)
        
        # Mirroring to documents (Serving)
        batch.set(self.db.collection("documents").document(doc_id), {
            "card_summary": summary_json,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        batch.set(self.db.collection("profiles").document(doc_id), {
            "process_flags": {"card": False}
        }, merge=True)
        
        batch.commit()
        logger.info(f"✅ [Card] 요약 완료: {summary_json.get('l1')}")
