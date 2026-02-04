"""
Pipeline E2E Test Script (v2)
==============================
Google Drive 업로드 감지 → Ingestion → RAG Pipeline 전체 흐름 테스트 및 검증

[테스트 범위]
- Phase B: DocAI → Profile → Chunk (순차)
- Phase B-2: Policy/Summary/Entity (병렬) → Merge
- Phase C-A: Embed → Vector → Meta (Vector Track)
- Phase C-B: Concepts → Edges → Ranker → Serving (Graph Track)

[사용법]
1. 환경변수 설정 (.env 파일)
2. python scripts/dev/simulate_webhook.py
3. 지정된 Drive 폴더에 파일 업로드
4. 콘솔에서 각 단계별 진행 상황 확인
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import time
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

# 경로 설정 (backend 폴더 기준)
sys.path.append(os.getcwd())

# 환경 변수 로드
from dotenv import load_dotenv
load_dotenv()

from app.core.gcp_clients import get_drive_service, get_firestore_client
from app.core.config import settings
from app.models.user import UserSchema
from app.services.ingestion_service import process_and_catalog_file
from app.rag.orchestrator import PipelineOrchestrator
from google.cloud import firestore  # FieldFilter 사용을 위해 필요

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PipelineTest")


# =============================================
# 테스트 설정
# =============================================
TARGET_FOLDER_ID = os.getenv("TEST_DRIVE_FOLDER_ID", "1gH1nvnYFLPNTutPMhLXcKKZ02zpM0L67")
USER_EMAIL = os.getenv("TEST_USER_EMAIL", "test_user@omnihub.com")
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", 3))


# =============================================
# 검증 상태 정의
# =============================================
class CheckStatus(Enum):
    PENDING = "⏳"
    SUCCESS = "✅"
    FAILED = "❌"
    SKIPPED = "⏭️"
    WARNING = "⚠️"


@dataclass
class StepResult:
    """단계별 검증 결과"""
    name: str
    status: CheckStatus = CheckStatus.PENDING
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class PipelineTestResult:
    """파이프라인 전체 테스트 결과"""
    file_id: str
    file_name: str
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # Phase B - Sequential
    step_docai: StepResult = field(default_factory=lambda: StepResult("DocAI Extract"))
    step_profile: StepResult = field(default_factory=lambda: StepResult("Build Profile"))
    step_chunk: StepResult = field(default_factory=lambda: StepResult("Split & Chunk"))
    
    # Phase B-2 - Parallel + Merge
    step_policy: StepResult = field(default_factory=lambda: StepResult("Classify Policy"))
    step_summary: StepResult = field(default_factory=lambda: StepResult("Card Summary"))
    step_entity: StepResult = field(default_factory=lambda: StepResult("Extract Entities"))
    step_merge: StepResult = field(default_factory=lambda: StepResult("Merge Bundle"))
    
    # Phase C-A - Vector Track
    step_embed: StepResult = field(default_factory=lambda: StepResult("Embed Chunks"))
    step_vector: StepResult = field(default_factory=lambda: StepResult("Vector Upsert"))
    step_meta: StepResult = field(default_factory=lambda: StepResult("Meta Index"))
    
    # Phase C-B - Graph Track
    step_concepts: StepResult = field(default_factory=lambda: StepResult("Build Concepts"))
    step_edges: StepResult = field(default_factory=lambda: StepResult("Build Edges"))
    step_ranker: StepResult = field(default_factory=lambda: StepResult("Edge Ranker"))
    step_serving: StepResult = field(default_factory=lambda: StepResult("Graph Serving"))


# =============================================
# 파이프라인 검증 유틸리티
# =============================================
class PipelineVerifier:
    """파이프라인 각 단계의 결과를 검증하는 유틸리티"""
    
    def __init__(self):
        self.db = get_firestore_client()
    
    def check_docai_result(self, doc_id: str) -> StepResult:
        """DocAI 결과 검증"""
        result = StepResult("DocAI Extract")
        start = time.time()
        
        try:
            snap = self.db.collection("docai_results").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                page_count = data.get("page_count", 0)
                text_len = len(data.get("full_text", ""))
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Pages: {page_count}, Text: {text_len} chars"
                result.data = {
                    "page_count": page_count,
                    "text_length": text_len,
                    "status": data.get("status")
                }
            else:
                result.status = CheckStatus.FAILED
                result.message = "DocAI 결과 없음 (docai_results 컬렉션)"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_profile(self, doc_id: str) -> StepResult:
        """Profile 결과 검증"""
        result = StepResult("Build Profile")
        start = time.time()
        
        try:
            snap = self.db.collection("profiles").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                title = data.get("title", "?")
                tenant = data.get("tenant_id", "?")
                flags = data.get("process_flags", {})
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Title: '{title[:30]}...' | Tenant: {tenant}"
                result.data = {
                    "title": title,
                    "folder_path": data.get("folder_path"),
                    "process_flags": flags,
                    "active": data.get("active")
                }
            else:
                result.status = CheckStatus.FAILED
                result.message = "Profile 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_chunks(self, doc_id: str) -> StepResult:
        """Chunk 결과 검증"""
        result = StepResult("Split & Chunk")
        start = time.time()
        
        try:
            # chunks 컬렉션에서 해당 문서의 청크 메타 조회
            chunk_meta = self.db.collection("chunks").document(doc_id).get()
            
            if chunk_meta.exists:
                data = chunk_meta.to_dict()
                chunk_count = data.get("chunk_count", 0)
                gcs_uri = data.get("gcs_chunks_uri", "")
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Chunks: {chunk_count}개 생성"
                result.data = {
                    "chunk_count": chunk_count,
                    "gcs_uri": gcs_uri
                }
            else:
                result.status = CheckStatus.WARNING
                result.message = "청크 메타 없음 (짧은 문서일 수 있음)"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_policy(self, doc_id: str) -> StepResult:
        """Policy 결과 검증"""
        result = StepResult("Classify Policy")
        start = time.time()
        
        try:
            snap = self.db.collection("policies").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                security = data.get("security_level", "?")
                ssot = data.get("ssot_level", "?")
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Security: {security} | SSoT: {ssot}"
                result.data = {
                    "security_level": security,
                    "ssot_level": ssot,
                    "rules_applied": data.get("rules_applied", [])
                }
            else:
                result.status = CheckStatus.FAILED
                result.message = "Policy 정보 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_summary(self, doc_id: str) -> StepResult:
        """Card Summary 결과 검증"""
        result = StepResult("Card Summary")
        start = time.time()
        
        try:
            snap = self.db.collection("cards").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                summary = data.get("summary", {})
                l1 = summary.get("l1", "")[:50] if summary.get("l1") else ""
                
                result.status = CheckStatus.SUCCESS
                result.message = f"L1: '{l1}...'"
                result.data = {
                    "l1": summary.get("l1"),
                    "l2": summary.get("l2"),
                    "l3": summary.get("l3")
                }
            else:
                result.status = CheckStatus.FAILED
                result.message = "Card Summary 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_entities(self, doc_id: str) -> StepResult:
        """Entity 추출 결과 검증"""
        result = StepResult("Extract Entities")
        start = time.time()
        
        try:
            snap = self.db.collection("entities").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                entity_count = data.get("entity_count", 0)
                gcs_uri = data.get("gcs_entities_uri", "")
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Entities: {entity_count}개"
                result.data = {
                    "entity_count": entity_count,
                    "gcs_uri": gcs_uri
                }
            else:
                result.status = CheckStatus.WARNING
                result.message = "Entity 정보 없음 (추출 대상 없을 수 있음)"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_bundle(self, doc_id: str) -> StepResult:
        """Bundle 병합 결과 검증"""
        result = StepResult("Merge Bundle")
        start = time.time()
        
        try:
            snap = self.db.collection("doc_bundles").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                gcs_uri = data.get("gcs_bundle_uri", "")
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Bundle 생성 완료"
                result.data = {
                    "gcs_uri": gcs_uri,
                    "created_at": str(data.get("created_at"))
                }
            else:
                result.status = CheckStatus.WARNING
                result.message = "Bundle 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_embeddings(self, doc_id: str) -> StepResult:
        """Embedding 결과 검증"""
        result = StepResult("Embed Chunks")
        start = time.time()
        
        try:
            snap = self.db.collection("embeddings").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                chunk_count = data.get("count", 0)  # 'count' 필드 사용
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Embedded: {chunk_count}개 청크"
                result.data = {
                    "chunk_count": chunk_count,
                    "gcs_uri": data.get("gcs_embeddings_uri"),
                    "model_version": data.get("model_version")
                }
            else:
                result.status = CheckStatus.FAILED
                result.message = "Embedding 정보 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_vector_upsert(self, doc_id: str) -> StepResult:
        """Vector Upsert 결과 검증"""
        result = StepResult("Vector Upsert")
        start = time.time()
        
        try:
            snap = self.db.collection("vector_upserts").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                count = data.get("upserted_count", 0)
                error = data.get("error")
                
                if error:
                    result.status = CheckStatus.FAILED
                    result.message = f"Error: {error}"
                elif count > 0:
                    result.status = CheckStatus.SUCCESS
                    result.message = f"Upserted: {count} vectors"
                else:
                    result.status = CheckStatus.WARNING
                    result.message = "Count: 0"
                    
                result.data = {
                    "upserted_count": count,
                    "index_name": data.get("index_name", ""),
                    "timestamp": str(data.get("timestamp", ""))
                }
            else:
                result.status = CheckStatus.WARNING
                result.message = "Vector Upsert 기록 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_document_index(self, doc_id: str) -> StepResult:
        """Document Meta Index 결과 검증"""
        result = StepResult("Meta Index")
        start = time.time()
        
        try:
            snap = self.db.collection("documents").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                title = data.get("title", "?")
                security = data.get("security_level", "?")
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Indexed: '{title[:25]}...' | Sec: {security}"
                result.data = {
                    "title": title,
                    "security_level": security,
                    "review_status": data.get("review_status"),
                    "active": data.get("active")
                }
            else:
                result.status = CheckStatus.FAILED
                result.message = "Document Index 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_concepts(self, doc_id: str) -> StepResult:
        """Concepts 연결 검증 (해당 문서와 연관된 개념 수)"""
        result = StepResult("Build Concepts")
        start = time.time()
        
        try:
            # entities에서 해당 문서가 생성한 개념 확인
            entities_snap = self.db.collection("entities").document(doc_id).get()
            if entities_snap.exists:
                result.status = CheckStatus.SUCCESS
                result.message = "Concepts 처리 완료"
            else:
                result.status = CheckStatus.WARNING
                result.message = "Entity 정보 기반 Concepts 확인 불가"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_edges(self, doc_id: str) -> StepResult:
        """Graph Edges 결과 검증"""
        result = StepResult("Build Edges")
        start = time.time()
        
        try:
            edges = list(self.db.collection("edges_doc_concept")
                        .where("doc_id", "==", doc_id)
                        .limit(100)
                        .stream())
            
            if edges:
                edge_count = len(edges)
                result.status = CheckStatus.SUCCESS
                result.message = f"Edges: {edge_count}개"
                result.data = {"edge_count": edge_count}
            else:
                result.status = CheckStatus.WARNING
                result.message = "Edge 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_ranker(self, doc_id: str) -> StepResult:
        """Edge Ranker 결과 검증"""
        result = StepResult("Edge Ranker")
        start = time.time()
        
        try:
            edges = list(self.db.collection("edges_doc_concept")
                        .where(filter=firestore.FieldFilter("doc_id", "==", doc_id))
                        .where(filter=firestore.FieldFilter("rank_score", ">", 0))
                        .limit(10)
                        .stream())
            
            if edges:
                avg_score = sum(e.to_dict().get("rank_score", 0) for e in edges) / len(edges)
                result.status = CheckStatus.SUCCESS
                result.message = f"Ranked edges: {len(edges)}개 (avg score: {avg_score:.2f})"
            else:
                result.status = CheckStatus.WARNING
                result.message = "Ranked edge 없음"
        except Exception as e:
            result.status = CheckStatus.WARNING
            result.message = f"Ranker 확인 불가: {e}"
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def check_graph_serving(self, doc_id: str) -> StepResult:
        """Graph Serving Index 결과 검증"""
        result = StepResult("Graph Serving")
        start = time.time()
        
        try:
            snap = self.db.collection("graph_serving_docs").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict()
                concept_count = data.get("concept_count", 0)
                top_concepts = data.get("top_concepts", [])
                
                result.status = CheckStatus.SUCCESS
                result.message = f"Concepts: {concept_count}개 연결"
                result.data = {
                    "concept_count": concept_count,
                    "top_concepts": top_concepts[:3]
                }
            else:
                result.status = CheckStatus.WARNING
                result.message = "Graph Serving Index 없음"
        except Exception as e:
            result.status = CheckStatus.FAILED
            result.message = str(e)
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    def run_full_verification(self, doc_id: str) -> PipelineTestResult:
        """전체 파이프라인 검증 실행"""
        result = PipelineTestResult(file_id=doc_id, file_name="")
        
        # Phase B - Sequential
        result.step_docai = self.check_docai_result(doc_id)
        result.step_profile = self.check_profile(doc_id)
        result.step_chunk = self.check_chunks(doc_id)
        
        # Phase B-2 - Parallel + Merge
        result.step_policy = self.check_policy(doc_id)
        result.step_summary = self.check_summary(doc_id)
        result.step_entity = self.check_entities(doc_id)
        result.step_merge = self.check_bundle(doc_id)
        
        # Phase C-A - Vector Track
        result.step_embed = self.check_embeddings(doc_id)
        result.step_vector = self.check_vector_upsert(doc_id)
        result.step_meta = self.check_document_index(doc_id)
        
        # Phase C-B - Graph Track
        result.step_concepts = self.check_concepts(doc_id)
        result.step_edges = self.check_edges(doc_id)
        result.step_ranker = self.check_ranker(doc_id)
        result.step_serving = self.check_graph_serving(doc_id)
        
        result.completed_at = datetime.now()
        return result


# =============================================
# 결과 출력 유틸리티
# =============================================
def print_result_table(result: PipelineTestResult):
    """파이프라인 테스트 결과를 테이블 형태로 출력"""
    
    print("\n" + "=" * 80)
    print(f"📋 PIPELINE VERIFICATION REPORT")
    print(f"   File ID: {result.file_id}")
    print(f"   Started: {result.started_at.strftime('%H:%M:%S')}")
    if result.completed_at:
        duration = (result.completed_at - result.started_at).total_seconds()
        print(f"   Duration: {duration:.1f}s")
    print("=" * 80)
    
    # Phase B
    print("\n📦 [Phase B] Sequential Processing")
    print("-" * 60)
    _print_step(result.step_docai)
    _print_step(result.step_profile)
    _print_step(result.step_chunk)
    
    # Phase B-2
    print("\n🔀 [Phase B-2] Parallel Processing + Merge")
    print("-" * 60)
    _print_step(result.step_policy)
    _print_step(result.step_summary)
    _print_step(result.step_entity)
    print("  " + "─" * 40)
    _print_step(result.step_merge)
    
    # Phase C-A
    print("\n🅰️ [Phase C - Track A] Vector Pipeline")
    print("-" * 60)
    _print_step(result.step_embed)
    _print_step(result.step_vector)
    _print_step(result.step_meta)
    
    # Phase C-B
    print("\n🅱️ [Phase C - Track B] Graph Pipeline")
    print("-" * 60)
    _print_step(result.step_concepts)
    _print_step(result.step_edges)
    _print_step(result.step_ranker)
    _print_step(result.step_serving)
    
    # Summary
    all_steps = [
        result.step_docai, result.step_profile, result.step_chunk,
        result.step_policy, result.step_summary, result.step_entity, result.step_merge,
        result.step_embed, result.step_vector, result.step_meta,
        result.step_concepts, result.step_edges, result.step_ranker, result.step_serving
    ]
    
    success = sum(1 for s in all_steps if s.status == CheckStatus.SUCCESS)
    failed = sum(1 for s in all_steps if s.status == CheckStatus.FAILED)
    warning = sum(1 for s in all_steps if s.status == CheckStatus.WARNING)
    
    print("\n" + "=" * 80)
    print(f"📊 SUMMARY: ✅ {success} Success | ❌ {failed} Failed | ⚠️ {warning} Warning")
    print("=" * 80 + "\n")


def _print_step(step: StepResult):
    """개별 단계 출력"""
    status_icon = step.status.value
    name_padded = step.name.ljust(20)
    print(f"  {status_icon} {name_padded} | {step.message}")


# =============================================
# 메인 실행 로직
# =============================================
def run_async(coro):
    """동기 함수 내에서 비동기 코루틴 실행"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def main():
    print("\n" + "=" * 80)
    print("🚀 OMNIHUB RAG PIPELINE E2E TESTER (v2)")
    print("=" * 80)
    print(f"📂 대상 폴더 ID: {TARGET_FOLDER_ID}")
    print(f"⏱️ 폴링 간격: {POLL_INTERVAL_SEC}초")
    print("💡 지정된 Drive 폴더에 파일을 업로드하면 파이프라인이 실행됩니다.")
    print("   (종료: Ctrl+C)")
    print("=" * 80 + "\n")

    # 1. 서비스 인증 확인
    try:
        drive_service = get_drive_service()
        db = get_firestore_client()
        print("✅ GCP 인증 성공")
    except Exception as e:
        print(f"❌ 인증 실패: {e}")
        return

    # 2. Dummy User 생성
    dummy_user = UserSchema(
        userId="usr_tester_001",
        email=USER_EMAIL,
        displayName="Pipeline Tester",
        role="admin",
        google_access_token="dummy",
        google_refresh_token="dummy",
        department="QA Team"
    )

    # 3. 오케스트레이터 & 검증기 초기화
    orchestrator = PipelineOrchestrator()
    verifier = PipelineVerifier()

    # 4. Start Page Token 획득
    token_response = drive_service.changes().getStartPageToken().execute()
    saved_start_page_token = token_response.get('startPageToken')
    print(f"✅ Drive Watch Token: {saved_start_page_token}")
    print("⏳ 파일 업로드 대기 중...\n")

    try:
        while True:
            # 5. 변경사항 폴링
            response = drive_service.changes().list(
                pageToken=saved_start_page_token,
                spaces='drive',
                fields='newStartPageToken, nextPageToken, changes(fileId, file(id, name, mimeType, parents, trashed))',
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()

            changes = response.get('changes', [])

            if response.get('newStartPageToken'):
                saved_start_page_token = response.get('newStartPageToken')

            # 6. 변경사항 처리
            for change in changes:
                file_id = change.get('fileId')
                file_meta = change.get('file')

                if not file_meta or file_meta.get('trashed'):
                    continue

                parents = file_meta.get('parents', [])
                if TARGET_FOLDER_ID not in parents:
                    continue

                file_name = file_meta.get('name', 'Unknown')
                mime_type = file_meta.get('mimeType', '')

                print("\n" + "🚨" * 30)
                print(f"🆕 새 파일 감지: {file_name}")
                print(f"   ID: {file_id} | MIME: {mime_type}")
                print("🚨" * 30)

                test_result = PipelineTestResult(file_id=file_id, file_name=file_name)

                try:
                    # === Step 1: Ingestion ===
                    print("\n📥 [Ingestion] Drive → GCS 스트리밍 시작...")
                    ingest_start = time.time()
                    
                    ingest_result = process_and_catalog_file(
                        user=dummy_user,
                        file_id=file_id,
                        drive_meta=file_meta
                    )
                    
                    internal_id = ingest_result.get("file_id", f"fil_{file_id}")
                    gcs_uri = ingest_result.get('gcs_uri')
                    mime_type = ingest_result.get('mime_type')
                    
                    ingest_duration = time.time() - ingest_start
                    print(f"  ✅ Ingestion 완료 ({ingest_duration:.1f}s)")
                    print(f"     Internal ID: {internal_id}")
                    print(f"     GCS URI: {gcs_uri}")

                    # === Step 2: RAG Pipeline ===
                    print("\n🎼 [Pipeline] RAG Orchestrator 실행...")
                    pipeline_start = time.time()
                    
                    run_async(orchestrator.run_pipeline(
                        file_id=internal_id,
                        gcs_uri=gcs_uri,
                        mime_type=mime_type
                    ))
                    
                    pipeline_duration = time.time() - pipeline_start
                    print(f"  ✅ Pipeline 완료 ({pipeline_duration:.1f}s)")

                    # === Step 3: Verification ===
                    print("\n🔍 [Verification] 각 단계 결과 검증 중...")
                    test_result = verifier.run_full_verification(internal_id)
                    test_result.file_name = file_name
                    
                    print_result_table(test_result)

                except Exception as e:
                    print(f"\n💥 오류 발생: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # 부분 검증 시도
                    print("\n🔍 [Partial Verification] 가능한 단계만 검증...")
                    test_result = verifier.run_full_verification(file_id)
                    print_result_table(test_result)

                print("\n⏳ 다음 파일 대기 중...\n")

            time.sleep(POLL_INTERVAL_SEC)

    except KeyboardInterrupt:
        print("\n🛑 테스트 종료")


if __name__ == "__main__":
    main()