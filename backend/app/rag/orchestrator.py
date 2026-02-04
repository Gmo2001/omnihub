"""
RAG Pipeline Orchestrator (v2)
==============================
Phase B: 순차 처리 (추출 → 정규화 → 청킹)
Phase B-2: 병렬 처리 (정책/요약/엔티티) + 병합
Phase C: 2트랙 병렬 (Vector / Graph)

[Cloud Run 제약사항 준수]
- 로컬 파일 저장 금지 (GCS/Firestore 사용)
- ADC 인증 사용 (하드코딩 금지)
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

# Step Imports
from app.rag.steps.run_docai_extract import DocAIExtractor
from app.rag.steps.build_profile import ProfileBuilder
from app.rag.steps.split_and_chunk import DocChunker
from app.rag.steps.classify_doc_policy import PolicyClassifier
from app.rag.steps.summarize_for_card import CardSummarizer
from app.rag.steps.extract_entities_relations import EntityExtractor
from app.rag.steps.merge_doc_artifacts import DocBundleMerger
from app.rag.steps.embed_chunks import ChunkEmbedder
from app.rag.steps.upsert_vector_index import VectorIndexUpserter
from app.rag.steps.upsert_doc_index_meta import DocIndexUpserter
from app.rag.steps.build_concepts import ConceptBuilder
from app.rag.steps.build_graph_edges import GraphEdgeBuilder
from app.rag.steps.edge_ranker import EdgeRanker
from app.rag.steps.build_graph_serving_index import GraphServingIndexBuilder

# Services
from app.services.tree_indexer_service import TreeIndexerService
from app.core.gcp_clients import get_firestore_client
from google.cloud import firestore

# Logger
logger = logging.getLogger("PipelineOrchestrator")
logger.setLevel(logging.INFO)


class PipelineOrchestrator:
    """
    RAG 파이프라인의 전체 실행 흐름을 관리하는 오케스트레이터.
    
    Pipeline Structure:
    ==================
    
    [Phase B - Sequential]
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │  1. DocAI   │──▶│  2. Profile │──▶│  3. Chunk   │
    │  (Extract)  │   │ (Normalize) │   │  (Split)    │
    └─────────────┘   └─────────────┘   └─────────────┘
                                               │
                                               ▼
    [Phase B-2 - Parallel + Merge]
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │  4. Policy  │   │  5. Summary │   │ 6. Entity   │  (Parallel)
    │  (Classify) │   │  (Card)     │   │  (NER/RE)   │
    └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
           │                 │                 │
           └────────────────┬┬─────────────────┘
                            ││
                            ▼▼
                    ┌─────────────┐
                    │  7. Merge   │
                    │  (Bundle)   │
                    └──────┬──────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
    [Phase C - Track A: Vector]     [Phase C - Track B: Graph]
    ┌─────────────┐                 ┌─────────────┐
    │  8. Embed   │                 │ 8. Concepts │
    │  (768-dim)  │                 │ (Normalize) │
    └──────┬──────┘                 └──────┬──────┘
           ▼                               ▼
    ┌─────────────┐                 ┌─────────────┐
    │ 9. Vector   │                 │ 9. Edges    │
    │ (Upsert)    │                 │ (Build)     │
    └──────┬──────┘                 └──────┬──────┘
           ▼                               ▼
    ┌─────────────┐                 ┌─────────────┐
    │ 10. Meta    │                 │ 10. Ranker  │
    │ (Index)     │                 │ (Score)     │
    └─────────────┘                 └──────┬──────┘
                                           ▼
                                    ┌─────────────┐
                                    │ 11. Serving │
                                    │ (Graph Idx) │
                                    └─────────────┘
    """
    
    def __init__(self):
        # Lazy Initialization (인스턴스 생성 시 초기화)
        self.db = get_firestore_client()
        
        # Phase B - Sequential Steps
        self.docai = DocAIExtractor()
        self.profiler = ProfileBuilder()
        self.chunker = DocChunker()
        
        # Phase B-2 - Parallel Steps
        self.classifier = PolicyClassifier()
        self.summarizer = CardSummarizer()
        self.extractor = EntityExtractor()
        self.merger = DocBundleMerger()
        
        # Phase C - Track A: Vector
        self.embedder = ChunkEmbedder()
        self.vector_upserter = VectorIndexUpserter()
        self.meta_upserter = DocIndexUpserter()
        
        # Phase C - Track B: Graph
        self.concept_builder = ConceptBuilder()
        self.edge_builder = GraphEdgeBuilder()
        self.ranker = EdgeRanker()
        self.graph_serving_builder = GraphServingIndexBuilder()
        
        # Additional Services
        self.tree_indexer = TreeIndexerService()
        
        # Thread Pool for parallel execution
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def run_pipeline(self, file_id: str, gcs_uri: str = None, mime_type: str = None):
        """
        파일에 대한 전체 RAG 파이프라인 실행
        
        Args:
            file_id: Firestore Document ID (File ID)
            gcs_uri: Source GCS URI (DocAI 단계에서 필요)
            mime_type: MIME Type
        """
        logger.info(f"🚀 [Pipeline] Start for {file_id}")
        
        try:
            # =============================================
            # Phase B: Sequential Processing
            # (추출 → 정규화 → 청킹)
            # =============================================
            await self._run_phase_b_sequential(file_id, gcs_uri, mime_type)
            
            # =============================================
            # Phase B-2: Parallel Processing + Merge
            # (정책/요약/엔티티 병렬 → 병합)
            # =============================================
            await self._run_phase_b_parallel(file_id)
            
            # =============================================
            # Phase C: Two-Track Parallel Processing
            # Track A: Vector (Embed → Upsert → Meta)
            # Track B: Graph (Concepts → Edges → Ranker → Serving)
            # =============================================
            await self._run_phase_c_parallel(file_id)
            
            # Pipeline 완료 상태 업데이트
            self._update_pipeline_status(file_id, "completed")
            logger.info(f"✨ [Pipeline] Completed for {file_id}")

        except Exception as e:
            logger.error(f"💥 [Pipeline] Failed at {file_id}: {e}", exc_info=True)
            self._update_pipeline_status(file_id, "failed", str(e))
            raise

    # =============================================
    # Phase B: Sequential Processing
    # =============================================
    async def _run_phase_b_sequential(self, file_id: str, gcs_uri: str = None, mime_type: str = None):
        """
        Phase B: 순차 처리 (추출 → 정규화 → 청킹)
        각 단계는 이전 단계의 결과에 의존하므로 순차 실행 필수
        """
        logger.info(f"📦 [Phase B] Sequential Processing Start")
        
        # Step 1: Document AI Extraction
        if gcs_uri and mime_type:
            logger.info(f"  → Step 1: DocAI Extraction")
            await self._run_in_executor(
                self.docai.process_single_document, 
                file_id, gcs_uri, mime_type
            )
        else:
            logger.info(f"  → Step 1: Skip DocAI (No GCS URI)")
        
        # Step 2: Profile Build (Normalize)
        logger.info(f"  → Step 2: Build Profile (Normalize)")
        await self._run_in_executor(self.profiler.process_single_document, file_id)
        
        # Step 2.5: Update Tree Index (On-the-fly)
        await self._update_tree_index(file_id)
        
        # Step 3: Split & Chunk
        logger.info(f"  → Step 3: Split & Chunk")
        await self._run_in_executor(self.chunker.process_single_document, file_id)
        
        logger.info(f"📦 [Phase B] Sequential Processing Complete")

    # =============================================
    # Phase B-2: Parallel Processing + Merge
    # =============================================
    async def _run_phase_b_parallel(self, file_id: str):
        """
        Phase B-2: 병렬 처리 후 병합
        정책/요약/엔티티를 병렬로 처리한 후 결과를 병합
        """
        logger.info(f"🔀 [Phase B-2] Parallel Processing Start")
        
        # Step 4, 5, 6: Parallel Execution (Policy, Summary, Entity)
        parallel_tasks = [
            self._run_in_executor(self.classifier.process_single_document, file_id),  # Policy
            self._run_in_executor(self.summarizer.process_single_document, file_id),  # Summary
            self._run_in_executor(self.extractor.process_single_document, file_id),   # Entity
        ]
        
        logger.info(f"  → Steps 4-6: Running Policy/Summary/Entity in parallel...")
        
        # 병렬 실행 대기
        results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
        
        # 에러 체크
        for i, result in enumerate(results):
            step_names = ["Policy", "Summary", "Entity"]
            if isinstance(result, Exception):
                logger.error(f"  ⚠️ Step {step_names[i]} failed: {result}")
                # 개별 단계 실패는 로깅 후 계속 진행 (선택적 정책)
        
        logger.info(f"  → Steps 4-6: Parallel execution complete")
        
        # Step 7: Merge Artifacts (Bundle)
        logger.info(f"  → Step 7: Merge Artifacts (Bundle)")
        await self._run_in_executor(self.merger.process_single_document, file_id)
        
        logger.info(f"🔀 [Phase B-2] Parallel Processing Complete")

    # =============================================
    # Phase C: Two-Track Parallel Processing
    # =============================================
    async def _run_phase_c_parallel(self, file_id: str):
        """
        Phase C: 2트랙 병렬 처리
        - Track A: Vector (Embed → VectorDB → MetaIndex)
        - Track B: Graph (Concepts → Edges → Ranker → ServingIndex)
        """
        logger.info(f"🎯 [Phase C] Two-Track Parallel Processing Start")
        
        # 두 트랙을 병렬로 실행
        track_tasks = [
            self._run_track_a_vector(file_id),
            self._run_track_b_graph(file_id),
        ]
        
        results = await asyncio.gather(*track_tasks, return_exceptions=True)
        
        # 트랙별 에러 체크
        track_names = ["Vector", "Graph"]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"  ⚠️ Track {track_names[i]} failed: {result}")
        
        logger.info(f"🎯 [Phase C] Two-Track Processing Complete")

    async def _run_track_a_vector(self, file_id: str):
        """
        Track A: Vector Search Pipeline
        Embed → VectorDB Upsert → Document Meta Index
        """
        logger.info(f"  🅰️ [Track A] Vector Pipeline Start")
        
        try:
            # Step 8: Embed Chunks
            logger.info(f"    → A-8: Embed Chunks")
            await self._run_in_executor(self.embedder.process_single_document, file_id)
            
            # Step 9: Vector DB Upsert
            logger.info(f"    → A-9: Vector DB Upsert")
            await self._run_in_executor(self.vector_upserter.process_single_document, file_id)
            
            # Step 10: Document Meta Index
            logger.info(f"    → A-10: Document Meta Index")
            await self._run_in_executor(self.meta_upserter.process_single_document, file_id)
            
            logger.info(f"  🅰️ [Track A] Vector Pipeline Complete")
            
        except Exception as e:
            logger.error(f"  🅰️ [Track A] Vector Pipeline Failed: {e}")
            raise

    async def _run_track_b_graph(self, file_id: str):
        """
        Track B: Knowledge Graph Pipeline
        Concepts → Edges → Ranker → Serving Index
        
        Note: Concepts는 배치 작업이지만, 단일 문서 모드에서는 
        해당 문서의 엔티티만으로 incremental update 수행
        """
        logger.info(f"  🅱️ [Track B] Graph Pipeline Start")
        
        try:
            # Step 8: Build/Update Concepts (Incremental)
            # 단일 문서 처리 시에는 전체 배치 대신 해당 문서만 처리
            logger.info(f"    → B-8: Update Concepts (Incremental)")
            await self._run_in_executor(self._update_concepts_for_doc, file_id)
            
            # Step 9: Build Graph Edges
            logger.info(f"    → B-9: Build Graph Edges")
            await self._run_in_executor(self.edge_builder.process_single_document, file_id)
            
            # Step 10: Edge Ranker
            logger.info(f"    → B-10: Edge Ranker")
            await self._run_in_executor(self.ranker.process_single_document, file_id)
            
            # Step 11: Graph Serving Index (Incremental)
            logger.info(f"    → B-11: Update Graph Serving Index")
            await self._run_in_executor(self._update_graph_serving_for_doc, file_id)
            
            logger.info(f"  🅱️ [Track B] Graph Pipeline Complete")
            
        except Exception as e:
            logger.error(f"  🅱️ [Track B] Graph Pipeline Failed: {e}")
            raise

    # =============================================
    # Helper Methods
    # =============================================
    async def _run_in_executor(self, func, *args):
        """
        동기 함수를 비동기 컨텍스트에서 실행
        ThreadPoolExecutor를 사용하여 블로킹 방지
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    async def _update_tree_index(self, file_id: str):
        """Tree Index 업데이트 (프로필 생성 후)"""
        try:
            profile_snap = self.db.collection("profiles").document(file_id).get()
            if profile_snap.exists:
                logger.info(f"  → Step 2.5: Update Tree Index")
                self.tree_indexer.process_single_doc(profile_snap.to_dict())
        except Exception as e:
            logger.warning(f"Tree Index update failed (non-critical): {e}")

    def _update_concepts_for_doc(self, file_id: str):
        """
        단일 문서에 대한 Concept 업데이트 (Incremental)
        해당 문서의 엔티티만 처리하여 관련 개념 업데이트
        """
        try:
            self.concept_builder.process_single_document(file_id)
        except Exception as e:
            logger.warning(f"Concept update failed: {e}")

    def _update_graph_serving_for_doc(self, file_id: str):
        """
        단일 문서에 대한 Graph Serving Index 업데이트 (Incremental)
        해당 문서와 연결된 개념들만 업데이트
        """
        try:
            self.graph_serving_builder.process_single_document(file_id)
        except Exception as e:
            logger.warning(f"Graph Serving Index update failed: {e}")

    def _update_pipeline_status(self, file_id: str, status: str, error_msg: str = None):
        """파이프라인 상태 업데이트"""
        update_data = {
            "pipeline_status": status,
            "pipeline_updated_at": firestore.SERVER_TIMESTAMP
        }
        if error_msg:
            update_data["pipeline_error"] = error_msg
            
        self.db.collection("files").document(file_id).set(update_data, merge=True)


# =============================================
# Batch Orchestrator (전체 재처리용)
# =============================================
class BatchOrchestrator:
    """
    배치 작업용 오케스트레이터
    전체 문서에 대한 파이프라인 재실행 또는 특정 단계만 실행
    """
    
    def __init__(self):
        self.db = get_firestore_client()
        self.concept_builder = ConceptBuilder()
        self.graph_serving_builder = GraphServingIndexBuilder()
        self.tree_indexer = TreeIndexerService()
    
    def run_full_concept_rebuild(self):
        """전체 Concept 재구축 (배치 작업)"""
        logger.info("🔄 [Batch] Full Concept Rebuild Start")
        self.concept_builder.run_batch()
        logger.info("🔄 [Batch] Full Concept Rebuild Complete")
    
    def run_full_graph_serving_rebuild(self):
        """전체 Graph Serving Index 재구축 (배치 작업)"""
        logger.info("🔄 [Batch] Full Graph Serving Index Rebuild Start")
        self.graph_serving_builder.run()
        logger.info("🔄 [Batch] Full Graph Serving Index Rebuild Complete")
    
    def run_full_tree_index_rebuild(self, tenant_id: str, engagement_id: str):
        """전체 Tree Index 재구축 (배치 작업)"""
        logger.info("🔄 [Batch] Full Tree Index Rebuild Start")
        self.tree_indexer.refresh_all(tenant_id, engagement_id)
        logger.info("🔄 [Batch] Full Tree Index Rebuild Complete")


# Singleton Instance (기존 호환성 유지)
orchestrator = PipelineOrchestrator()
