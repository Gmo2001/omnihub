import os
import json
import logging
import hashlib
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

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
    
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE_HINT", 1000))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP_HINT", 200))
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.PROJECT_ID: missing.append("GCP_PROJECT_ID")
        if not cls.GCS_BUCKET: missing.append("GCS_BUCKET")
        if missing:
            raise ValueError(f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("SplitAndChunk")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class SplitAndChunk:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.storage = storage.Client(project=Config.PROJECT_ID)
        self.bucket = self.storage.bucket(Config.GCS_BUCKET)

    def load_docai_artifact(self, artifact_uri: str) -> Dict[str, Any]:
        """GCS에서 DocAI 결과 JSON 로드"""
        if not artifact_uri.startswith("gs://"):
            return None
        
        blob_path = artifact_uri.replace(f"gs://{Config.GCS_BUCKET}/", "")
        blob = self.bucket.blob(blob_path)
        
        try:
            content = blob.download_as_text(encoding='utf-8')
            return json.loads(content)
        except Exception as e:
            logger.error(f"DocAI Artifact 로드 실패 ({artifact_uri}): {e}")
            raise

    def naive_text_chunking(self, text: str, size: int, overlap: int) -> List[Dict[str, Any]]:
        """간단한 Character-based Rolling Window (Token 기반 추천하지만 여기선 Char 기반 운영 최소)"""
        chunks = []
        if not text:
            return chunks
        
        length = len(text)
        start = 0
        
        while start < length:
            end = min(start + size, length)
            
            # 단어 잘림 방지는 여기서 생략 (운영 시에는 공백 기준 search 필요)
            chunk_text = text[start:end]
            
            # 너무 짧은 나머지 부분은 처리?
            if len(chunk_text) < 50 and start > 0:
                pass # 그냥 포함
            
            chunks.append({
                "text": chunk_text,
                "start_char_idx": start,
                "end_char_idx": end
            })
            
            if end == length:
                break
                
            start += (size - overlap)
            
        return chunks

    def process_document(self, doc_snapshot):
        # 1. 문서 정보 로드
        doc_id = doc_snapshot.id
        profile_data = doc_snapshot.to_dict()
        
        # 필터링
        flags = profile_data.get("process_flags", {})
        if flags.get("chunk") is False:
             # logger.debug(f"SKIP {doc_id}: Already Chunked")
             return

        logger.info(f"Chunking {doc_id}...")
        
        docai_uri = profile_data.get("docai_artifact_uri")
        content_hash = profile_data.get("doc_content_hash")
        
        if not docai_uri:
            logger.warning(f"SKIP {doc_id}: DocAI Artifact URI 없음")
            return

        try:
            # 2. DocAI Artifact 로드
            artifact = self.load_docai_artifact(docai_uri)
            full_text = artifact.get("full_text", "")
            pages = artifact.get("pages", [])
            
            all_chunks = []
            
            # 3. 텍스트 청킹 (Naive)
            # 개선: 페이지별로 청킹 vs 전체 텍스트 청킹
            # 일반적인 RAG는 전체 텍스트 청킹이 문맥 유지에 유리
            # 단, page_no를 매핑해줘야 함.
            
            text_chunks = self.naive_text_chunking(full_text, Config.CHUNK_SIZE, Config.CHUNK_OVERLAP)
            
            for idx, tc in enumerate(text_chunks):
                # Page Number 추정 (Offset 기반)
                # DocAI가 준 pages[i].text_segments 정보를 쓰면 완벽하지만 복잡함.
                # 여기서는 운영 최소: pages 배열을 순회하며 글자수 누적해서 매핑
                
                # 간단 매핑: 단순 텍스트 검색이나 누적 Length 사용 (정확도 낮을 수 있음)
                # 여기선 일단 page_no = -1 (Unknown) 또는 1로 고정하지 않고
                # Artifact에 페이지별 텍스트 길이가 있다면 그걸로 추산.
                # run_docai_extract.py에서 artifact['pages']에 text 필드를 넣어놨음.
                
                # 정석: DocAI Shard Text들을 합쳤으므로, 누적 Offset 비교
                page_start, page_end = self.guess_page_range(tc['start_char_idx'], tc['end_char_idx'], pages)
                
                chunk_id = f"{doc_id}:chunk:{idx}"
                all_chunks.append({
                    "chunk_id": chunk_id,
                    "type": "text",
                    "text": tc['text'],
                    "span": {"start": tc['start_char_idx'], "end": tc['end_char_idx']},
                    "page_start_no": page_start,
                    "page_end_no": page_end,
                    "tokens_estimate": len(tc['text']) // 4 # heuristic
                })

            # 4. (옵션) 테이블 청크 처리
            # artifact['tables'] 가 있다면 이를 별도 청크로 생성
            if artifact.get("tables"):
                for t_idx, tbl in enumerate(artifact['tables']):
                    chunk_id = f"{doc_id}:table:{t_idx}"
                    # Table을 JSON Dump 또는 Markdown 변환
                    table_text = json.dumps(tbl['rows'], ensure_ascii=False)
                    page_no = tbl.get("page_no")
                    
                    all_chunks.append({
                        "chunk_id": chunk_id,
                        "type": "table",
                        "text": table_text, # Embed 용
                        "data": tbl, # 구조화 데이터
                        "page_start_no": page_no,
                        "page_end_no": page_no,
                        "tokens_estimate": len(table_text) // 4
                    })

            # 5. GCS 저장 (Chunks JSON)
            # gs://{bucket}/chunks/{doc_id}/{hash}/chunks.json
            chunks_blob_path = f"chunks/{doc_id}/{content_hash}/chunks.json"
            chunks_blob = self.bucket.blob(chunks_blob_path)
            chunks_blob.upload_from_string(
                json.dumps(all_chunks, ensure_ascii=False),
                content_type="application/json"
            )
            chunks_gcs_uri = f"gs://{Config.GCS_BUCKET}/{chunks_blob_path}"
            
            # 6. Firestore 업데이트
            # chunks/{doc_id}
            self.db.collection("chunks").document(doc_id).set({
                "doc_id": doc_id,
                "doc_content_hash": content_hash,
                "gcs_chunks_uri": chunks_gcs_uri,
                "chunk_count": len(all_chunks),
                "created_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            # 7. Flag Off
            self.db.collection("profiles").document(doc_id).set({
                "process_flags": {"chunk": False}
            }, merge=True)
            
            logger.info(f"SUCCESS {doc_id}: {len(all_chunks)} chunks created.")

        except Exception as e:
            logger.error(f"FAIL {doc_id}: {e}")

    def guess_page_range(self, start_offset, end_offset, pages):
        """텍스트 오프셋이 어느 페이지에 걸쳐있는지 추정"""
        # pages가 텍스트 길이를 가지고 있다고 가정.
        # run_docai_extract.py에서 'text'를 넣어뒀음.
        
        current_pos = 0
        start_page = None
        end_page = None
        
        for p in pages:
            p_len = len(p.get("text", ""))
            p_start = current_pos
            p_end = current_pos + p_len
            current_pos += p_len
            
            # 청크의 시작이 이 페이지 안에 있는가
            if start_page is None and start_offset < p_end:
                 start_page = p.get("page_no", 1)
            
            # 청크의 끝이 이 페이지 안에 있는가 (혹은 지났는가)
            if end_offset <= p_end:
                end_page = p.get("page_no", 1)
                break
        
        # 마지막까지 못 찾았으면 마지막 페이지
        if start_page is None and pages: start_page = pages[-1].get("page_no")
        if end_page is None and pages: end_page = pages[-1].get("page_no")
        
        return start_page, end_page


    def run_batch(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        logger.info("Split & Chunk 작업 시작...")
        
        # process_flags.chunk == True or None (최초)
        # 하지만 여기선 편의상 active=True 인 모든 profiles 대상 -> 코드 내에서 flag check
        docs = self.db.collection("profiles").where(filter=firestore.FieldFilter("active", "==", True)).stream()
        
        count = 0
        for doc in docs:
            self.process_document(doc)
            count += 1
            
        logger.info(f"작업 완료. 총 {count}개 문서 확인.")

if __name__ == "__main__":
    chunker = SplitAndChunk()
    chunker.run_batch()
