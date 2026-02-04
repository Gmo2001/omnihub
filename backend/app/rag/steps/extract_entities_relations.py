import json
import logging
import time
import os
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("EntityExtractor")
logger.setLevel(logging.INFO)

class EntityExtractor:
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
        
        # Config (Types)
        # TODO: Load from file if exists, else default
        # Config (Types)
        # Load rules from text file
        self.types = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT", "PRODUCT", "TECHNOLOGY"]
        types_file = os.path.join("app", "rag", "rules", "entity_types.txt")
        
        if os.path.exists(types_file):
            try:
                with open(types_file, "r", encoding="utf-8") as f:
                    # 빈 줄 제외하고 대문자로 변환하여 리스트 생성
                    self.types = [line.strip() for line in f if line.strip()]
                logger.info(f"Loaded {len(self.types)} entity types from {types_file}")
            except Exception as e:
                logger.warning(f"Failed to load entity types: {e}")
        else:
            logger.warning(f"Entity types file not found at {types_file}. Using defaults.")
        self.types_str = ", ".join(self.types)

    def extract(self, text: str):
        prompt = f"""
        You are an advanced Information Extraction system.
        Extract meaningful Entities and Relations from the following text based on the allowed types.
        
        Allowed Entity Types: {self.types_str}
        
        Format Requirements:
        - Output Must be valid JSON.
        - JSON Structure:
          {{
            "entities": [ {{"name": "...", "type": "...", "aliases": ["..."]}} ],
            "relations": [ {{"src": "...", "rel_type": "...", "dst": "..."}} ]
          }}
        - Limit to key entities (exclude trivial ones).
        - Keep names normalized (e.g. 'Apple Inc.' instead of 'Apple').
        
        Input Text:
        {text[:20000]}
        
        Output JSON:
        """
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json\n", "").replace("json", "")
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"LLM Extract Fail: {e}")
            return {"entities": [], "relations": []}

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

        logger.info(f"🕸️ [Entity] 추출 시작: {doc_id}")

        chunk_ref = self.db.collection("chunks").document(doc_id).get()
        if not chunk_ref.exists: return
        
        chunks = self.load_chunks(chunk_ref.get("gcs_chunks_uri"))
        if not chunks: return

        # Selection Strategy (Simpler version)
        # Top 5 text chunks
        text_chunks = [c for c in chunks if c.get("type", "text") == "text"]
        target_chunks = text_chunks[:5]
        
        if not target_chunks: return
        
        # [Parallel Extraction]
        # 병렬 처리로 속도 개선 (기존: 텍스트 병합 후 1회 호출 -> 변경: 5개 청크 동시 호출)
        import concurrent.futures
        
        final_entities = []
        all_relations = []
        source_link = profile.get("source_link")
        
        def _process_chunk(chunk):
            """Thread Worker Function"""
            text = chunk.get("text", "")
            if not text: return None
            # Chunk 단위 추출
            return self.extract(text)

        # ThreadPoolExecutor를 사용해 병렬 LLM 호출 (IO Bound)
        # max_workers=5: 적절한 동시성을 유지하며 Rate Limit 방지
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Future와 Chunk 매핑
            future_to_chunk = {executor.submit(_process_chunk, c): c for c in target_chunks}
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_data = future_to_chunk[future]
                try:
                    extracted = future.result()
                    if not extracted: continue
                    
                    # 결과 병합 및 증거(Evidence) 매핑
                    for ent in extracted.get("entities", []):
                        ent["evidence"] = [{
                            "doc_id": doc_id,
                            "chunk_id": chunk_data.get("chunk_id"),
                            "page": chunk_data.get("page_start_no"),
                            "source_link": source_link,
                            "snippet": "Extracted from chunk context",
                            "span": None
                        }]
                        final_entities.append(ent)
                        
                    for rel in extracted.get("relations", []):
                        rel["evidence_chunk_id"] = chunk_data.get("chunk_id")
                        all_relations.append(rel)
                        
                except Exception as e:
                    logger.error(f"Chunk processing failed (chunk_id={chunk_data.get('chunk_id')}): {e}")

        logger.info(f"⚡ [Entity] 병렬 추출 완료: {len(target_chunks)} chunks -> {len(final_entities)} entities")

        # Save to GCS
        content_hash = profile.get("doc_content_hash", "nohash")
        gcs_path = f"entities/{doc_id}/{content_hash}/entities.json"
        blob = self.bucket.blob(gcs_path)
        payload = {
            "doc_id": doc_id,
            "entities": final_entities,
            "relations": all_relations,
            "created_at": time.time()
        }
        blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        
        # Firestore Update
        self.db.collection("entities").document(doc_id).set({
            "doc_id": doc_id,
            "gcs_entities_uri": gcs_uri,
            "entity_count": len(final_entities),
            "relation_count": len(all_relations),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        self.db.collection("documents").document(doc_id).set({
            "entity_count": len(final_entities)
        }, merge=True)
        
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"entities": False}
        }, merge=True)
        
        logger.info(f"✅ [Entity] 추출 완료: {len(final_entities)} entities")
