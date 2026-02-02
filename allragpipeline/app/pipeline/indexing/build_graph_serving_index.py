import os
import logging
from collections import defaultdict
from typing import Dict, Any, List
from dotenv import load_dotenv
from app.common.enums import ReviewStatus

from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    SERVING_VERSION = os.getenv("GRAPH_SERVING_INDEX_VERSION", "v1")
    PER_NODE_CAP = int(os.getenv("PER_NODE_CAP", 50))
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("GraphServingBuilder")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class GraphServingIndexBuilder:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        
        # In-Memory Aggregators
        self.doc_neighbors = defaultdict(list)     # doc_id -> list of concepts
        self.concept_neighbors = defaultdict(list) # concept_id -> list of docs
        
        # Cache
        self.valid_docs = set()
        self.valid_concepts = set()


    def load_valid_docs(self):
        """Scan documents for filtering (active=True AND review_status=APPROVED)
        """
        logger.info("Loading valid docs (APPROVED only)...")
        docs = (self.db.collection("documents")
            .where("tenant_id", "==", Config.TENANT_ID)
            .where("engagement_id", "==", Config.ENGAGEMENT_ID)
            .where("active", "==", True)
            .where("review_status", "==", ReviewStatus.APPROVED.value)
            .stream())
            
        for d in docs:
            self.valid_docs.add(d.id)
            
        logger.info(f"Valid Docs: {len(self.valid_docs)}")

    def load_concepts_meta(self):
        """Load minimal concept meta (type, name) for serving"""
        # 전체 concept를 다 메모리에 올리는 것은 위험할 수 있으나, 2~3천개 수준이면 OK
        # 많으면 on-demand lookup으로 변경해야 함
        logger.info("Loading concepts...")
        concepts = (self.db.collection("concepts")
            .where("tenant_id", "==", Config.TENANT_ID)
            .where("engagement_id", "==", Config.ENGAGEMENT_ID)
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
            .where("tenant_id", "==", Config.TENANT_ID)
            .where("engagement_id", "==", Config.ENGAGEMENT_ID)
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
            top_k = neighbors[:Config.PER_NODE_CAP]
            
            payload = {
                "doc_id": doc_id,
                "tenant_id": Config.TENANT_ID,
                "engagement_id": Config.ENGAGEMENT_ID,
                "top_concepts": top_k,
                "concept_count": len(neighbors),
                "version": Config.SERVING_VERSION,
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
            top_k = neighbors[:Config.PER_NODE_CAP]
            
            payload = {
                "concept_id": concept_id,
                "tenant_id": Config.TENANT_ID,
                "engagement_id": Config.ENGAGEMENT_ID,
                "top_docs": top_k,
                "doc_count": len(neighbors),
                "meta": self.concept_meta.get(concept_id, {}),
                "version": Config.SERVING_VERSION,
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
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        self.load_valid_docs()
        self.load_concepts_meta()
        self.aggregate_edges()
        self.build_serving_indexes()

if __name__ == "__main__":
    builder = GraphServingIndexBuilder()
    builder.run()
