import os
import json
import logging
from typing import Dict, Any, List

from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("DocChunker")
logger.setLevel(logging.INFO)

class DocChunker:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output") # Default fallback
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        
        # Config
        self.chunk_size = int(getattr(settings, "CHUNK_SIZE_HINT", 1000))
        self.chunk_overlap = int(getattr(settings, "CHUNK_OVERLAP_HINT", 200))

    def load_docai_artifact(self, artifact_uri: str) -> Dict[str, Any]:
        if not artifact_uri.startswith("gs://"): return None
        blob_path = artifact_uri.replace(f"gs://{self.bucket_name}/", "")
        # Handle cross-bucket if needed, but assuming same bucket for now
        # If bucket name is strictly GCS_BUCKET, use that.
        blob = self.bucket.blob(blob_path)
        try:
            content = blob.download_as_text(encoding='utf-8')
            return json.loads(content)
        except Exception as e:
            logger.error(f"DocAI Artifact Load Fail: {e}")
            raise

    def naive_text_chunking(self, text: str, size: int, overlap: int) -> List[Dict[str, Any]]:
        chunks = []
        if not text: return chunks
        length = len(text)
        start = 0
        while start < length:
            end = min(start + size, length)
            chunk_text = text[start:end]
            if len(chunk_text) < 50 and start > 0: pass 
            chunks.append({
                "text": chunk_text,
                "start_char_idx": start,
                "end_char_idx": end
            })
            if end == length: break
            start += (size - overlap)
        return chunks

    def guess_page_range(self, start_offset, end_offset, pages):
        """텍스트 오프셋 -> 페이지 매핑"""
        current_pos = 0
        start_page = None
        end_page = None
        
        for p in pages:
            p_len = len(p.get("text", ""))
            p_start = current_pos
            p_end = current_pos + p_len
            current_pos += p_len
            
            if start_page is None and start_offset < p_end:
                start_page = p.get("page_no", 1)
            
            if end_offset <= p_end:
                end_page = p.get("page_no", 1)
                break
        
        if start_page is None and pages: start_page = pages[-1].get("page_no")
        if end_page is None and pages: end_page = pages[-1].get("page_no")
        
        return start_page, end_page

    def process_single_document(self, doc_id: str):
        """Orchestrator 호출 포인트"""
        
        # 1. Profile 조회
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists:
            logger.warning(f"SKIP Chunk: Profile not found {doc_id}")
            return
        
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active"): return

        logger.info(f"✂️ [Chunk] 청킹 시작: {doc_id}")
        
        # docai_artifact_uri? or gcs_uris.docai_json?
        # build_profile에서 gcs_uris['docai_json']에 저장함.
        gcs_uris = profile_data.get("gcs_uris", {})
        docai_uri = gcs_uris.get("docai_json")
        content_hash = profile_data.get("doc_content_hash")
        
        if not docai_uri:
            # Fallback: check legacy (docai_results collection)
            # Or direct query to docai_results
            res_ref = self.db.collection("docai_results").document(doc_id).get()
            if res_ref.exists:
                docai_uri = res_ref.get("raw_output_uri") # This is Prefix usually
                # Need to fetch merged JSON? 
                # run_docai_extract.py saves full_text and pages in Firestore!
                # SplitAndChunk.py logic relies on loading JSON from GCS.
                # If run_docai_extract SAVED merged JSON to GCS, we use that.
                # But looking at run_docai_extract, it saves result_doc to Firestore.
                # It does NOT seem to save a merged "artifact.json" to GCS explicitly, 
                # passed only 'raw_output_uri' which is a folder of shards.
                # Wait! SplitAndChunk logic `load_docai_artifact` expects a JSON file.
                pass

        # [Important] SplitAndChunkLogic divergence
        # Original script `load_docai_artifact` loads a single JSON file.
        # But `run_docai_extract` output is raw shards in GCS + merged text in Firestore.
        # We should use Firestore data if available, to avoid re-reading GCS shards.
        
        # Let's verify `docai_results` schema in Firestore
        res_ref = self.db.collection("docai_results").document(doc_id).get()
        if not res_ref.exists:
            logger.warning("SKIP Chunk: DocAI Results missing")
            return
            
        docai_result = res_ref.to_dict()
        full_text = docai_result.get("full_text", "")
        pages = docai_result.get("pages", [])
        
        # Proceed with Chunking using Firestore Data
        all_chunks = []
        text_chunks = self.naive_text_chunking(full_text, self.chunk_size, self.chunk_overlap)
        
        for idx, tc in enumerate(text_chunks):
            page_start, page_end = self.guess_page_range(tc['start_char_idx'], tc['end_char_idx'], pages)
            chunk_id = f"{doc_id}:chunk:{idx}"
            all_chunks.append({
                "chunk_id": chunk_id,
                "type": "text",
                "text": tc['text'],
                "span": {"start": tc['start_char_idx'], "end": tc['end_char_idx']},
                "page_start_no": page_start,
                "page_end_no": page_end,
                "tokens_estimate": len(tc['text']) // 4
            })

        # Save to GCS (Chunks)
        chunks_blob_path = f"chunks/{doc_id}/{content_hash}/chunks.json"
        chunks_blob = self.bucket.blob(chunks_blob_path)
        chunks_blob.upload_from_string(
            json.dumps(all_chunks, ensure_ascii=False),
            content_type="application/json"
        )
        chunks_gcs_uri = f"gs://{self.bucket_name}/{chunks_blob_path}"
        
        # Firestore Update (Top-level meta)
        self.db.collection("chunks").document(doc_id).set({
            "doc_id": doc_id,
            "doc_content_hash": content_hash,
            "gcs_chunks_uri": chunks_gcs_uri,
            "chunk_count": len(all_chunks),
            "created_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # Flag Off
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"chunk": False}
        }, merge=True)
        
        logger.info(f"✅ [Chunk] 생성 완료: {len(all_chunks)} chunks")
