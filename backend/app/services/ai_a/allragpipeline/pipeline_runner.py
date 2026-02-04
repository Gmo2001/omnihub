import os
import sys
import argparse
import subprocess
import logging
import time
import uuid
import json
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# Logger 설정
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("PipelineRunner")

class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    MAX_WORKERS = 8 # [Optimization] Increased for concurrency (requires 4GB+ Memory)
    LOCK_TIMEOUT_SEC = 300 # 5분

class PipelineRunner:
    # ... (omitted) ...

    def run(self):
        self._log_run_start()
        
        try:
            # --- Phase A: Sequential ---
            logger.info("=== Phase A: Initial Processing ===")
            self.run_step("A_sync_drive_to_gcs")
            self.run_step("A_extract_file_meta")
            # self.run_step("A_fetch_drive_meta") # extract_file_meta와 유사, 순서상 필요하면 추가
            self.run_step("A_run_docai_extract")
            self.run_step("A_build_profile")
            
            # --- Phase B: Parallel Document Processing ---
            logger.info("=== Phase B: Parallel Processing ===")
            
            # [Fix] Sequence Dependency: Chunking MUST happen before Analysis
            # Group 1: Preparation (Chunking & Policy)
            b_steps_prep = [
                "B_classify_doc_policy",
                "B_split_and_chunk"
            ]
            
            with ThreadPoolExecutor(max_workers=min(len(b_steps_prep), self.args.max_workers)) as executor:
                futures = {executor.submit(self.run_step, step): step for step in b_steps_prep}
                for future in as_completed(futures):
                    step = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        raise RuntimeError(f"Prep step {step} failed") from e

            # Group 2: Analysis (Requires Chunks)
            b_steps_analysis = [
                "B_summarize_for_card",
                "B_extract_entities_relations"
            ]
            
            with ThreadPoolExecutor(max_workers=min(len(b_steps_analysis), self.args.max_workers)) as executor:
                futures = {executor.submit(self.run_step, step): step for step in b_steps_analysis}
                for future in as_completed(futures):
                    step = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        raise RuntimeError(f"Analysis step {step} failed") from e

            # Merge
            self.run_step("B_merge_doc_artifacts")
            
            # --- Phase C: Global & Edge Processing ---
            logger.info("=== Phase C: Knowledge Graph & Embedding ===")
            
            # Global Merge (Locked)
            self.run_step("C_build_concepts")
            
            # Parallel Edges & Embeds
            c_parallel_steps = ["C_build_graph_edges", "C_embed_chunks"]
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(self.run_step, step): step for step in c_parallel_steps}
                for future in as_completed(futures):
                    try: 
                        future.result() 
                    except Exception: 
                        raise

            # Edge Ranker (Optional)
            try:
                self.run_step("C_edge_ranker")
            except Exception as e:
                logger.warning(f"Edge Ranker optional step failed: {e}")

            # --- Phase D: Indexing ---
            logger.info("=== Phase D: Indexing ===")
            # 기본 순차 실행 (안전성)
            self.run_step("D_upsert_vector_index")
            self.run_step("D_upsert_doc_index_meta")
            self.run_step("D_build_graph_serving_index")
            self.run_step("D_build_tree_index") # Added Tree Index
            
            self._log_run_end("SUCCESS")
            
        except Exception as e:
            logger.error(f"Pipeline Failed: {e}")
            self._log_run_end("FAILED", e)
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Omnihub RAG Pipeline Runner")
    parser.add_argument("--doc_id", required=True, help="Target Document ID")
    parser.add_argument("--tenant_id", required=True, help="Tenant ID")
    parser.add_argument("--engagement_id", required=True, help="Engagement ID")
    parser.add_argument("--mode", default="full", choices=["full", "resume"], help="Execution Mode")
    parser.add_argument("--max_workers", type=int, default=4, help="Parallel workers count")
    parser.add_argument("--force_global", action="store_true", help="Force run global steps in resume mode")
    
    args = parser.parse_args()
    
    runner = PipelineRunner(args)
    runner.run()
