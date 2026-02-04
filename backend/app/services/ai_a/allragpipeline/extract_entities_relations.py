import os
import json
import logging
import time
import concurrent.futures
from typing import List, Dict, Any, Optional, Set
from dotenv import load_dotenv

from google.cloud import firestore
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel

# 로컬 환경 변수 로드
load_dotenv()

if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    GCS_BUCKET = os.getenv("GCS_BUCKET")
    GCS_PREFIX = os.getenv("GCS_PREFIX", "omnihub")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "vertex").lower()
    VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
    VERTEX_MODEL = os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-exp")
    
    EXTRACTOR_VERSION = os.getenv("ENTITY_EXTRACTOR_VERSION", "v1")
    ENTITY_TYPES_FILE = "rules/entity_types.txt"
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    
    MAX_ENTITIES = 200
    MAX_RELATIONS = 300

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")
        if not cls.GCS_BUCKET: raise ValueError("GCS_BUCKET 누락")
        if not os.path.exists(cls.ENTITY_TYPES_FILE):
             raise ValueError(f"Entity Types File Not Found: {cls.ENTITY_TYPES_FILE}")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("EntityExtractor")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- LLM Wrapper ---
class EntityExtractorLLM:
    def __init__(self, types: List[str]):
        if Config.LLM_PROVIDER == 'vertex':
            vertexai.init(project=Config.PROJECT_ID, location=Config.VERTEX_LOCATION)
            self.model = GenerativeModel(Config.VERTEX_MODEL)
        else:
            raise NotImplementedError
        self.types_str = ", ".join(types)

    def extract(self, text: str) -> Dict[str, Any]:
        """청크 텍스트에서 엔티티/관계 추출"""
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

# --- Core Logic ---
class EntityExtractor:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)
        
        # Load Types
        with open(Config.ENTITY_TYPES_FILE, "r") as f:
            self.types = [line.strip() for line in f.readlines() if line.strip()]
            
        self.llm = EntityExtractorLLM(self.types)

    def load_chunks(self, chunks_uri: str) -> List[Dict[str, Any]]:
        # GCS에서 Chunks 로드 (가벼운 버전)
        # 만약 Chunks가 너무 많으면 일부만 로드하거나, 중요 페이지 위주로 로드해야 함
        # 여기선 상위 N개 + Table Chunk 로드 로직 구현
        blob_path = chunks_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        content = blob.download_as_text()
        all_chunks = json.loads(content)
        
        # 선택 로직: 앞부분 + 테이블 + 일정 간격 등
        # 지금은 상위 5개 + Table 전체
        selected = []
        text_count = 0
        for c in all_chunks:
            if c.get("type") == "table":
                selected.append(c)
            elif text_count < 5: # Text Chunk 상위 5개
                selected.append(c)
                text_count += 1
        
        return selected

    def process_document(self, doc_snapshot):
        doc_id = doc_snapshot.id
        profile = doc_snapshot.to_dict()
        
        flags = profile.get("process_flags", {})
        if flags.get("entities") is False:
             return

        logger.info(f"Extracting Entities for {doc_id}...")
        
        # 1. Chunk 로드
        chunk_ref = self.db.collection("chunks").document(doc_id).get()
        if not chunk_ref.exists:
            logger.warning("SKIP: Chunks not found")
            return
            
        chunks_uri = chunk_ref.get("gcs_chunks_uri")
        chunks = self.load_chunks(chunks_uri)
        
        all_entities = {} # name:alias -> entity obj (merge logic)
        all_relations = []
        
        chunks.sort(key=lambda x: x.get("chunk_id", ""))

        # 2. Key Chunk Selection
        # - Intro: Top 3
        # - Outro: Last 2
        # - Page Leaders: First chunk of each page
        
        target_indices = set()
        total_chunks = len(chunks)
        
        # Intro
        for i in range(min(3, total_chunks)):
            target_indices.add(i)
            
        # Outro
        for i in range(max(0, total_chunks - 2), total_chunks):
            target_indices.add(i)
            
        # Page Leaders
        visited_pages = set()
        for idx, chunk in enumerate(chunks):
            page = chunk.get("page_start_no")
            if page and page not in visited_pages:
                target_indices.add(idx)
                visited_pages.add(page)
        
        # Sort indices to maintain order
        sorted_indices = sorted(list(target_indices))
        target_chunks = [chunks[i] for i in sorted_indices]
        
        if not target_chunks:
            logger.warning("SKIP: No target chunks selected")
            return

        # 3. Combine Text
        combined_text = ""
        for tc in target_chunks:
            txt = tc.get("text", "")
            if txt:
                combined_text += f"{txt}\n\n"
        
        # Safety Limit (30k chars)
        if len(combined_text) > 30000:
            combined_text = combined_text[:30000]
            
        # 4. Single LLM Extraction
        logger.info(f"Extracting from {len(target_chunks)} key chunks (Length: {len(combined_text)} chars)...")
        extracted = self.llm.extract(combined_text)
        
        # 5. Process Result
        # Representative Evidence (First chunk of the selection)
        rep_chunk = target_chunks[0]
        rep_chunk_id = rep_chunk.get("chunk_id")
        rep_page = rep_chunk.get("page_start_no")
        source_link = profile.get("source_link")

        # Entity Merge
        for ent in extracted.get("entities", []):
            key = ent.get("name")
            if not key: continue
            
            if key not in all_entities:
                all_entities[key] = {
                    "name": key,
                    "type": ent.get("type", "OTHERS"),
                    "aliases": set(ent.get("aliases", [])),
                    "evidence": []
                }
            else:
                all_entities[key]["aliases"].update(ent.get("aliases", []))
                
            # Evidence 추가 (Representative)
            # 중복 방지 (이미 같은 chunk_id 증거가 있으면 스킵)
            if not any(e["chunk_id"] == rep_chunk_id for e in all_entities[key]["evidence"]):
                evidence_obj = {
                    "doc_id": doc_id,
                    "chunk_id": rep_chunk_id,
                    "page": rep_page,
                    "source_link": source_link,
                    "snippet": "Extracted from Key Chunks Summary", # Snippet is hard to pinpoint in combined text
                    "span": None
                }
                all_entities[key]["evidence"].append(evidence_obj)

        # Relation Accumulate
        for rel in extracted.get("relations", []):
            rel["evidence_chunk_id"] = rep_chunk_id
            all_relations.append(rel)
                
        # 3. Post-Process (Cap & List Convert)
        final_entities = []
        for v in all_entities.values():
            v["aliases"] = list(v["aliases"]) # set -> list
            final_entities.append(v)
            
        # Limit Cap
        final_entities = final_entities[:Config.MAX_ENTITIES]
        all_relations = all_relations[:Config.MAX_RELATIONS]
        
        # 4. Save to GCS (Volume이 클 수 있음)
        # gs://{bucket}/entities/{doc_id}/{hash}/entities.json
        content_hash = profile.get("doc_content_hash")
        gcs_path = f"entities/{doc_id}/{content_hash}/entities.json"
        blob = self.bucket.blob(gcs_path)
        
        payload = {
            "doc_id": doc_id,
            "entities": final_entities,
            "relations": all_relations,
            "extractor_version": Config.EXTRACTOR_VERSION,
            "model_version": Config.VERTEX_MODEL,
            "created_at": time.time()
        }
        
        blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")
        gcs_uri = f"gs://{Config.GCS_BUCKET}/{gcs_path}"
        
        # 5. Firestore Pointer Save
        self.db.collection("entities").document(doc_id).set({
            "doc_id": doc_id,
            "gcs_entities_uri": gcs_uri,
            "entity_count": len(final_entities),
            "relation_count": len(all_relations),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # Documents Stats Update
        self.db.collection("documents").document(doc_id).set({
            "entity_count": len(final_entities),
        }, merge=True)
        
        # Flag Off
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"entities": False}
        }, merge=True)
        
        logger.info(f"SUCCESS {doc_id}: Found {len(final_entities)} Entities, {len(all_relations)} Relations")

    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Entity Extraction 병렬 작업 시작...")
        
        # 1. 문서 목록 확보
        docs = list(self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).get())
        
        # 2. Worker 수 설정 (Quota 고려: 3~5 권장)
        max_workers = 5 
        
        count = 0
        try:
            # 3. ThreadPoolExecutor 병렬 처리
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_doc = {executor.submit(self.process_document, doc): doc for doc in docs}
                
                for future in concurrent.futures.as_completed(future_to_doc):
                    doc = future_to_doc[future]
                    try:
                        future.result()
                        count += 1
                    except Exception as e:
                        logger.error(f"FAIL {doc.id}: {e}")
        except KeyboardInterrupt:
            logger.info("사용자에 의해 중단되었습니다. (KeyboardInterrupt)")
            # Executor는 with 블록을 빠져나가며 정리됨
                    
        logger.info(f"병렬 작업 완료. 총 {count}개 문서 처리.")

if __name__ == "__main__":
    extractor = EntityExtractor()
    extractor.run_batch()
