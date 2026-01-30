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
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    MAX_WORKERS = 4
    LOCK_TIMEOUT_SEC = 300 # 5분

class PipelineRunner:
    def __init__(self, args):
        self.args = args
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.steps_ref = self.db.collection("pipeline_runs").document(self.run_id).collection("steps")
        self.doc_run_ref = self.db.collection("doc_runs").document(args.doc_id)
        
        # Step 파일 매핑
        self.step_map = {
            "A_sync_drive_to_gcs": "sync_drive_to_gcs.py",
            "A_extract_file_meta": "extract_file_meta.py",
            "A_fetch_drive_meta": "fetch_drive_meta.py",
            "A_run_docai_extract": "run_docai_extract.py",
            "A_build_profile": "build_profile.py",
            
            "B_classify_doc_policy": "classify_doc_policy.py",
            "B_split_and_chunk": "split_and_chunk.py",
            "B_summarize_for_card": "summarize_for_card.py",
            "B_extract_entities_relations": "extract_entities_relations.py",
            "B_merge_doc_artifacts": "merge_doc_artifacts.py",
            
            "C_build_concepts": "build_concepts.py",
            "C_build_graph_edges": "build_graph_edges.py",
            "C_embed_chunks": "embed_chunks.py",
            "C_edge_ranker": "edge_ranker.py",
            
            "D_upsert_vector_index": "upsert_vector_index.py",
            "D_upsert_doc_index_meta": "upsert_doc_index_meta.py",
            "D_build_graph_serving_index": "build_graph_serving_index.py",
            "D_build_tree_index": "build_tree_index.py"
        }

    def _log_run_start(self):
        self.db.collection("pipeline_runs").document(self.run_id).set({
            "run_id": self.run_id,
            "doc_id": self.args.doc_id,
            "tenant_id": self.args.tenant_id,
            "engagement_id": self.args.engagement_id,
            "status": "RUNNING",
            "mode": self.args.mode,
            "started_at": firestore.SERVER_TIMESTAMP,
            "version": os.getenv("PIPELINE_RUNNER_VERSION", "v1")
        })
        logger.info(f"Pipeline Run Started: {self.run_id} for Doc: {self.args.doc_id}")

    def _log_run_end(self, status="SUCCESS", error=None):
        data = {
            "status": status,
            "finished_at": firestore.SERVER_TIMESTAMP
        }
        if error:
            data["error"] = str(error)
            
        self.db.collection("pipeline_runs").document(self.run_id).set(data, merge=True)
        
        # Doc Run 요약 업데이트
        doc_update = {
            "last_run_id": self.run_id,
            "last_run_at": firestore.SERVER_TIMESTAMP,
            "last_status": status
        }
        if status == "SUCCESS":
            doc_update["last_success_run_id"] = self.run_id
        if error:
            doc_update["last_error"] = str(error)
            
        self.doc_run_ref.set(doc_update, merge=True)
        logger.info(f"Pipeline Run Finished: {status}")

    def _should_skip(self, step_name):
        if self.args.mode != "resume":
            return False
        
        # Resume 모드: 이전 실행 기록 확인 (여기서는 doc_runs의 last_run_id를 참조해야 정확하지만,
        # 편의상 '현재 런' 내에서의 스킵은 아니고, '과거 런'의 성공 여부를 봐야 함.
        # 하지만 run_id가 매번 새로 따지므로, 이 로직은 '같은 run_id 재시도'가 아니라 
        # 'doc_id 기준 최근 성공 스텝 스킵'이어야 함.
        
        # 운영 최소: doc_runs -> last_success_run_id -> steps 확인? 복잡함.
        # 단순화: doc_runs에 step_status 맵을 관리한다고 가정하거나,
        # 그냥 이번 런은 무조건 실행하되 내부적으로 멱등성 보장 믿음.
        
        # 사용자 요구사항: Firestore에서 doc_id의 마지막 run 상태를 보고...
        # -> doc_runs/{doc_id} -> steps_status 필드 (map) 관리 필요.
        # 아니면 가장 최근 run_id를 조회해서 그 run의 step status 확인.
        
        try:
            doc_snap = self.doc_run_ref.get()
            if not doc_snap.exists: return False
            
            last_run_id = doc_snap.get("last_run_id")
            if not last_run_id: return False
            
            # 이전 런의 해당 스텝 상태 확인
            step_ref = self.db.collection("pipeline_runs").document(last_run_id).collection("steps").document(step_name)
            step_snap = step_ref.get()
            if step_snap.exists and step_snap.get("status") == "SUCCESS":
                # 전역 스텝 예외 (force_global) - build_concepts
                if step_name == "C_build_concepts" and getattr(self.args, "force_global", False):
                    logger.info(f"Step {step_name} forcing execution despite previous success.")
                    return False
                    
                logger.info(f"Skipping {step_name} (Previously SUCCESS in {last_run_id})")
                return True
                
        except Exception as e:
            logger.warning(f"Resume check failed for {step_name}: {e}")
            
        return False

    def _run_step_subprocess(self, step_name):
        """실제 서브프로세스 실행"""
        script_file = self.step_map.get(step_name)
        if not script_file:
            raise ValueError(f"Unknown step: {step_name}")
            
        if not os.path.exists(script_file):
            # 경로 문제면 ./ 접두어 시도 등
             if os.path.exists(os.path.join(".", script_file)):
                 script_file = os.path.join(".", script_file)
             else:
                 raise FileNotFoundError(f"Script not found: {script_file}")

        # Firestore 기록: PENDING -> RUNNING
        step_doc_ref = self.steps_ref.document(step_name)
        step_doc_ref.set({
            "status": "RUNNING",
            "started_at": firestore.SERVER_TIMESTAMP,
            "inputs": {
                "doc_id": self.args.doc_id,
                "tenant_id": self.args.tenant_id,
                "engagement_id": self.args.engagement_id
            }
        })

        start_ts = time.time()
        
        cmd = [
            sys.executable, script_file,
            "--doc_id", self.args.doc_id,
            "--tenant_id", self.args.tenant_id,
            "--engagement_id", self.args.engagement_id
        ]
        
        logger.info(f"Step Running: {step_name}...")
        
        try:
            # Run Process with Timeout (10 minutes)
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            
            # SUCCESS
            duration_ms = int((time.time() - start_ts) * 1000)
            step_doc_ref.set({
                "status": "SUCCESS",
                "finished_at": firestore.SERVER_TIMESTAMP,
                "duration_ms": duration_ms,
                "stdout_tail": result.stdout[-1000:] if result.stdout else ""
            }, merge=True)
            logger.info(f"Step SUCCESS: {step_name} ({duration_ms}ms)")
            return True

        except subprocess.TimeoutExpired as e:
            # TIMEOUT
            duration_ms = int((time.time() - start_ts) * 1000)
            step_doc_ref.set({
                "status": "FAILED",
                "error": {
                    "type": "TimeoutExpired", 
                    "message": f"Step timed out after {e.timeout}s",
                    "stdout": e.stdout[-1000:] if e.stdout else "",
                    "stderr": e.stderr[-1000:] if e.stderr else ""
                },
                "finished_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
            logger.error(f"Step TIMEOUT: {step_name} after {e.timeout}s")
            raise RuntimeError(f"Step {step_name} timed out")
            
        except subprocess.CalledProcessError as e:
            # FAILED
            duration_ms = int((time.time() - start_ts) * 1000)
            error_info = {
                "type": "ProcessError",
                "message": str(e),
                "stderr": e.stderr[-2000:] if e.stderr else "",
                "stdout": e.stdout[-1000:] if e.stdout else ""
            }
            step_doc_ref.set({
                "status": "FAILED",
                "finished_at": firestore.SERVER_TIMESTAMP,
                "duration_ms": duration_ms,
                "error": error_info
            }, merge=True)
            logger.error(f"Step FAILED: {step_name}\nError: {e.stderr}")
            raise RuntimeError(f"Step {step_name} failed")
        except Exception as e:
            # Unexpected Error
            step_doc_ref.set({
                "status": "FAILED",
                "error": {"type": "Exception", "message": str(e), "trace": traceback.format_exc()}
            }, merge=True)
            logger.error(f"Step CRASHED: {step_name}: {e}")
            raise e

    def run_step(self, step_name):
        if self._should_skip(step_name):
            return

        if step_name == "C_build_concepts":
            self._run_with_lock(step_name)
        else:
            self._run_step_subprocess(step_name)

    def _run_with_lock(self, step_name):
        """전역 락 획득 후 실행"""
        lock_ref = self.db.collection("global_locks").document(step_name)
        
        # 1. Try Acquire Lock
        transaction = self.db.transaction()
        acquired = False
        
        @firestore.transactional
        def acquire_lock(txn, ref):
            res = txn.get(ref)
            
            # Safe handler for generator vs snapshot
            snapshot = None
            if hasattr(res, "__iter__") and not hasattr(res, "exists"): # Check if it's purely an iterable
                 try:
                     snapshot = next(iter(res))
                 except StopIteration:
                     pass # Nothing found
            else:
                 snapshot = res
            
            now = time.time()
            if snapshot and snapshot.exists:
                data = snapshot.to_dict()
                locked_at = data.get("locked_at", 0)
                if now - locked_at < Config.LOCK_TIMEOUT_SEC:
                    return False # Locked by other
            
            txn.set(ref, {
                "locked_at": now,
                "run_id": self.run_id,
                "doc_id": self.args.doc_id
            })
            return True

        # Simple retry for lock
        for _ in range(5):
            if acquire_lock(transaction, lock_ref):
                acquired = True
                break
            logger.warning(f"Waiting for global lock: {step_name}...")
            time.sleep(2)
            
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for {step_name}")
            
        try:
            self._run_step_subprocess(step_name)
        finally:
            lock_ref.delete() # Release Lock

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
            b_steps = [
                "B_classify_doc_policy",
                "B_split_and_chunk",
                "B_summarize_for_card",
                "B_extract_entities_relations"
            ]
            
            with ThreadPoolExecutor(max_workers=min(len(b_steps), self.args.max_workers)) as executor:
                futures = {executor.submit(self.run_step, step): step for step in b_steps}
                for future in as_completed(futures):
                    step = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        raise RuntimeError(f"Parallel step {step} failed") from e

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
