import logging
import asyncio
from typing import Optional, List

# Service Imports
from app.rag.steps.run_docai_extract import DocAIExtractor
from app.rag.steps.build_profile import ProfileBuilder
from app.rag.steps.classify_doc_policy import PolicyClassifier
from app.rag.steps.split_and_chunk import DocChunker
from app.rag.steps.summarize_for_card import CardSummarizer
from app.rag.steps.extract_entities_relations import EntityExtractor
from app.rag.steps.merge_doc_artifacts import DocBundleMerger
from app.rag.steps.build_graph_edges import GraphEdgeBuilder
from app.rag.steps.edge_ranker import EdgeRanker
from app.rag.steps.embed_chunks import ChunkEmbedder
from app.rag.steps.upsert_vector_index import VectorIndexUpserter
from app.rag.steps.upsert_doc_index_meta import DocIndexUpserter
from app.services.tree_indexer_service import TreeIndexerService
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("PipelineOrchestrator")
logger.setLevel(logging.INFO)

class PipelineOrchestrator:
    """
    RAG 파이프라인의 전체 실행 흐름을 관리하는 오케스트레이터.
    각 단계(Step)별 서비스들을 순차적/병렬적으로 호출하고 에러를 핸들링합니다.
    """
    def __init__(self):
        self.docai = DocAIExtractor()
        self.profiler = ProfileBuilder()
        self.classifier = PolicyClassifier()
        self.chunker = DocChunker()
        self.summarizer = CardSummarizer()
        self.extractor = EntityExtractor()
        self.merger = DocBundleMerger()
        self.edge_builder = GraphEdgeBuilder()
        self.ranker = EdgeRanker()
        self.embedder = ChunkEmbedder()
        self.vector_upserter = VectorIndexUpserter()
        self.vector_upserter = VectorIndexUpserter()
        self.meta_upserter = DocIndexUpserter()
        self.tree_indexer = TreeIndexerService()
        self.db = get_firestore_client()

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
            # Step 1. Document AI Extraction
            if gcs_uri and mime_type:
                logger.info(f" -> Step 1: DocAI Extraction")
                # DocAI wrapper is sync, be careful in async context
                self.docai.process_single_document(file_id, gcs_uri, mime_type)
            else:
                logger.info(f" -> Step 1: Skip (No GCS URI info provided)")

            # Step 2. Profile Build
            logger.info(f" -> Step 2: Build Profile")
            # Step 2. Profile Build
            logger.info(f" -> Step 2: Build Profile")
            self.profiler.process_single_document(file_id)

            # Step 2.5. Update Tree Index (On-the-fly)
            profile_snap = self.db.collection("profiles").document(file_id).get()
            if profile_snap.exists:
                logger.info(f" -> Step 2.5: Update Tree Index")
                self.tree_indexer.process_single_doc(profile_snap.to_dict())

            # Step 3. Classification (Policy)
            logger.info(f" -> Step 3: Classify Policy")
            self.classifier.process_single_document(file_id)

            # Step 4. Chunking
            logger.info(f" -> Step 4: Split & Chunk")
            self.chunker.process_single_document(file_id)
            
            # Step 5. Summarize (Card)
            logger.info(f" -> Step 5: Card Summary")
            self.summarizer.process_single_document(file_id)
            
            # Step 6. Extract Entities
            logger.info(f" -> Step 6: Entity Extraction")
            self.extractor.process_single_document(file_id)

            # Step 7. Merge Artifacts (Bundle)
            logger.info(f" -> Step 7: Merge Bundle")
            self.merger.process_single_document(file_id)

            # Step 8. Graph (Edge & Rank)
            # Note: build_concepts is a batch job, not per-doc. 
            # We assume concepts exist or are skipped.
            logger.info(f" -> Step 8: Build Edges & Rank")
            self.edge_builder.process_single_document(file_id)
            self.ranker.process_single_document(file_id)
            
            # Step 9. Embedding
            logger.info(f" -> Step 9: Embed Chunks")
            self.embedder.process_single_document(file_id)
            
            # Step 10. Vector Upsert
            logger.info(f" -> Step 10: Vector Upsert")
            self.vector_upserter.process_single_document(file_id)
            
            # Step 11. Doc Index Meta (Serving)
            logger.info(f" -> Step 11: Index Meta")
            self.meta_upserter.process_single_document(file_id)
            
            logger.info(f"✨ [Pipeline] Pipeline Execution Ended for {file_id}")

        except Exception as e:
            logger.error(f"💥 [Pipeline] Failed at {file_id}: {e}")
            # 에러 상태 업데이트 로직 추가 가능
            # get_firestore_client().collection("files").document(file_id).update({"pipeline_status": "failed"})

# Singleton Instance
orchestrator = PipelineOrchestrator()
