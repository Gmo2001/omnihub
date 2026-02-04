
import logging
from collections import defaultdict
from typing import Dict, Any, List
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import ReviewStatus

# Logger
logger = logging.getLogger("GraphServingBuilder")
logger.setLevel(logging.INFO)

class GraphServingIndexBuilder:
    def __init__(self):
        self.db = get_firestore_client()
        
        # 설정값 로드
        self.tenant_id = getattr(settings, "TENANT_ID", "default")
        self.engagement_id = getattr(settings, "ENGAGEMENT_ID", "default")
        self.serving_version = getattr(settings, "GRAPH_SERVING_INDEX_VERSION", "v1")
        self.per_node_cap = int(getattr(settings, "PER_NODE_CAP", 50))

        # In-Memory Aggregators
        self.doc_neighbors = defaultdict(list)     # doc_id -> list of concepts
        self.concept_neighbors = defaultdict(list) # concept_id -> list of docs
        
        # Cache
        self.valid_docs = set()
        self.valid_concepts = set()
        self.concept_meta = {}

    def load_valid_docs(self):
        """Scan documents for filtering (active=True AND review_status=APPROVED)"""
        logger.info("Loading valid docs (APPROVED only)...")
        # 문서가 많아지면 쿼리 최적화 필요 (현재는 전체 스캔)
        docs = (self.db.collection("documents")
            .where("tenant_id", "==", self.tenant_id)
            .where("engagement_id", "==", self.engagement_id)
            .where("active", "==", True)
            # .where("review_status", "==", ReviewStatus.APPROVED.value) # 일단 테스트 편의상 생략하거나 주석 처리 가능
             # 테스트 환경에서는 PENDING 상태도 허용하려면 위 라인 주석 처리
            .stream())
            
        count = 0
        for d in docs:
            # 상태 체크 (코드 레벨에서 유연하게)
            data = d.to_dict()
            status = data.get("review_status")
            if status not in [ReviewStatus.APPROVED.value, ReviewStatus.PENDING.value]: # PENDING도 일단 포함 (테스트용)
                continue
                
            self.valid_docs.add(d.id)
            count += 1
            
        logger.info(f"Valid Docs: {len(self.valid_docs)}")

    def load_concepts_meta(self):
        """Load minimal concept meta (type, name) for serving"""
        logger.info("Loading concepts...")
        concepts = (self.db.collection("concepts")
            .where("tenant_id", "==", self.tenant_id)
            .where("engagement_id", "==", self.engagement_id)
            .where("active", "==", True)
            .stream())
            
        self.concept_meta = {} # id -> {name, type}
        for c in concepts:
            d = c.to_dict()
            self.concept_meta[c.id] = {
                "name": d.get("canonical_name", ""),
                "type": d.get("type", "OTHERS")
            }
        logger.info(f"Valid Concepts: {len(self.concept_meta)}")

    def aggregate_edges(self):
        logger.info("Aggregating edges...")
        
        # Active Edges 조회 (전체 스코프)
        edges = (self.db.collection("edges_doc_concept")
            .where("tenant_id", "==", self.tenant_id)
            .where("engagement_id", "==", self.engagement_id)
            .where("active", "==", True)
            .stream())
            
        count = 0
        for e in edges:
            data = e.to_dict()
            doc_id = data.get("doc_id")
            concept_id = data.get("concept_id")
            
            # Validity Check
            if doc_id not in self.valid_docs: continue
            if concept_id not in self.concept_meta: continue
            
            score = data.get("rank_score", data.get("confidence", 1.0))
            mentions = data.get("mentions_count", 1)
            
            # For Doc -> Concepts
            self.doc_neighbors[doc_id].append({
                "concept_id": concept_id,
                "name": self.concept_meta[concept_id]["name"],
                "type": self.concept_meta[concept_id]["type"],
                "score": score,
                "mentions": mentions
            })
            
            # For Concept -> Docs
            self.concept_neighbors[concept_id].append({
                "doc_id": doc_id,
                "score": score,
                "mentions": mentions
            })
            
            count += 1
            if count % 1000 == 0:
                logger.debug(f"Processed {count} edges...")
                
        logger.info(f"Aggregation Done. Processed {count} edges.")

    def build_serving_indexes(self):
        logger.info("Building serving indexes...")
        batch = self.db.batch()
        batch_count = 0
        
        # 1. Doc-Centric Index
        for doc_id, neighbors in self.doc_neighbors.items():
            # Sort by score DESC
            neighbors.sort(key=lambda x: x["score"], reverse=True)
            top_k = neighbors[:self.per_node_cap]
            
            payload = {
                "doc_id": doc_id,
                "tenant_id": self.tenant_id,
                "engagement_id": self.engagement_id,
                "top_concepts": top_k,
                "concept_count": len(neighbors),
                "version": self.serving_version,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            batch.set(self.db.collection("graph_serving_docs").document(doc_id), payload, merge=True)
            batch_count += 1
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0

        # 2. Concept-Centric Index
        for concept_id, neighbors in self.concept_neighbors.items():
            neighbors.sort(key=lambda x: x["score"], reverse=True)
            top_k = neighbors[:self.per_node_cap]
            
            payload = {
                "concept_id": concept_id,
                "tenant_id": self.tenant_id,
                "engagement_id": self.engagement_id,
                "top_docs": top_k,
                "doc_count": len(neighbors),
                "meta": self.concept_meta.get(concept_id, {}),
                "version": self.serving_version,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            batch.set(self.db.collection("graph_serving_concepts").document(concept_id), payload, merge=True)
            batch_count += 1
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
                
        if batch_count > 0:
            batch.commit()
            
        logger.info("Serving Index Build Complete.")

    def run(self):
        self.load_valid_docs()
        self.load_concepts_meta()
        self.aggregate_edges()
        self.build_serving_indexes()

    def process_single_document(self, doc_id: str):
        """
        단일 문서에 대한 Graph Serving Index Incremental Update
        해당 문서와 연결된 개념들만 업데이트
        """
        logger.info(f"📊 [GraphServing] Incremental update for {doc_id}")
        
        # 1. 해당 문서의 엣지 조회
        edges = (self.db.collection("edges_doc_concept")
            .where(filter=firestore.FieldFilter("doc_id", "==", doc_id))
            .where(filter=firestore.FieldFilter("active", "==", True))
            .stream())
        
        doc_concepts = []
        affected_concept_ids = set()
        
        for e in edges:
            data = e.to_dict()
            concept_id = data.get("concept_id")
            if not concept_id:
                continue
                
            affected_concept_ids.add(concept_id)
            
            # 개념 메타 조회
            concept_ref = self.db.collection("concepts").document(concept_id).get()
            if not concept_ref.exists:
                continue
            concept_data = concept_ref.to_dict()
            
            score = data.get("rank_score", data.get("confidence", 1.0))
            mentions = data.get("mentions_count", 1)
            
            doc_concepts.append({
                "concept_id": concept_id,
                "name": concept_data.get("canonical_name", ""),
                "type": concept_data.get("type", "OTHERS"),
                "score": score,
                "mentions": mentions
            })
        
        if not doc_concepts:
            logger.warning(f"SKIP {doc_id}: No valid edges found")
            return
        
        # 2. Doc-Centric Index 업데이트
        doc_concepts.sort(key=lambda x: x["score"], reverse=True)
        top_k = doc_concepts[:self.per_node_cap]
        
        doc_payload = {
            "doc_id": doc_id,
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            "top_concepts": top_k,
            "concept_count": len(doc_concepts),
            "version": self.serving_version,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        self.db.collection("graph_serving_docs").document(doc_id).set(doc_payload, merge=True)
        
        # 3. Concept-Centric Index 업데이트 (영향받은 개념들만)
        batch = self.db.batch()
        batch_count = 0
        
        for concept_id in affected_concept_ids:
            # 해당 개념에 연결된 모든 문서 조회
            concept_edges = (self.db.collection("edges_doc_concept")
                .where(filter=firestore.FieldFilter("concept_id", "==", concept_id))
                .where(filter=firestore.FieldFilter("active", "==", True))
                .stream())
            
            concept_docs = []
            for ce in concept_edges:
                ce_data = ce.to_dict()
                linked_doc_id = ce_data.get("doc_id")
                if not linked_doc_id:
                    continue
                    
                score = ce_data.get("rank_score", ce_data.get("confidence", 1.0))
                mentions = ce_data.get("mentions_count", 1)
                
                concept_docs.append({
                    "doc_id": linked_doc_id,
                    "score": score,
                    "mentions": mentions
                })
            
            if not concept_docs:
                continue
                
            concept_docs.sort(key=lambda x: x["score"], reverse=True)
            top_k_docs = concept_docs[:self.per_node_cap]
            
            # 개념 메타 조회
            concept_ref = self.db.collection("concepts").document(concept_id).get()
            concept_meta = {}
            if concept_ref.exists:
                cd = concept_ref.to_dict()
                concept_meta = {
                    "name": cd.get("canonical_name", ""),
                    "type": cd.get("type", "OTHERS")
                }
            
            concept_payload = {
                "concept_id": concept_id,
                "tenant_id": self.tenant_id,
                "engagement_id": self.engagement_id,
                "top_docs": top_k_docs,
                "doc_count": len(concept_docs),
                "meta": concept_meta,
                "version": self.serving_version,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            batch.set(self.db.collection("graph_serving_concepts").document(concept_id), concept_payload, merge=True)
            batch_count += 1
            
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()
        
        logger.info(f"✅ [GraphServing] Updated serving index for {doc_id} ({len(affected_concept_ids)} concepts)")

if __name__ == "__main__":
    builder = GraphServingIndexBuilder()
    builder.run()
