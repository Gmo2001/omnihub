import os
import math
import logging
import time
from collections import defaultdict
from typing import Dict, Any, List
from dotenv import load_dotenv

from google.cloud import firestore

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    
    TENANT_ID = os.getenv("TENANT_ID")
    ENGAGEMENT_ID = os.getenv("ENGAGEMENT_ID")
    
    PER_DOC_CAP = int(os.getenv("PER_DOC_CAP", 50))
    RANKER_VERSION = os.getenv("EDGE_RANKER_VERSION", "v1")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID: raise ValueError("GCP_PROJECT_ID 누락")

# --- Logger ---
def setup_logger():
    logger = logging.getLogger("EdgeRanker")
    logger.setLevel(Config.LOG_LEVEL)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

logger = setup_logger()

# --- Core Logic ---
class EdgeRanker:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        # concept cache: concept_id -> df
        self.concept_df = {} 

    def load_concept_df(self):
        """Build Concept DF Cache for scoring (TF-IDF like)"""
        logger.info("Loading Concept DF stats...")
        # Scope Filter Enforced
        concepts = (self.db.collection("concepts")
            .where("tenant_id", "==", Config.TENANT_ID)
            .where("engagement_id", "==", Config.ENGAGEMENT_ID)
            .where("active", "==", True)
            .stream())
        count = 0
        for c in concepts:
            data = c.to_dict()
            self.concept_df[c.id] = data.get("doc_frequency", 1)
            count += 1
        logger.info(f"Loaded {count} concepts DF.")

    def calculate_score(self, edge: Dict[str, Any]) -> float:
        """
        Rank Score = Base * Bonus
        Base = Confidence (0.0~1.0)
        Bonus = IDF-like (1 + log(TotalDocs/DF)) - 여기선 간단히 1/log(1+DF) 형태 사용
                (너무 흔하면 점수 낮게, 희소하면 높게)
        """
        confidence = edge.get("confidence", 1.0)
        mentions = edge.get("mentions_count", 1)
        concept_id = edge.get("concept_id")
        
        df = self.concept_df.get(concept_id, 1)
        if df < 1: df = 1
        
        # Scarcity Bonus (희소성 보너스)
        # 많이 언급될수록(DF가 클수록) 점수가 낮아지는 로직
        # Log 스케일 적용
        scarcity = 10.0 / (math.log(1 + df) + 1.0)
        
        # Mention Count Bonus (해당 문서 내 중요도)
        local_importance = math.log(1 + mentions)
        
        score = confidence * scarcity * local_importance
        return round(score, 4)

    def process_edges_per_doc(self):
        """문서별로 Edge를 그룹화하여 랭킹 및 저장"""
        logger.info("Scanning active edges (Scoped)...")
        
        # 1. Active Edges 조회 -> Driven by Profiles
        # Scope Filter Enforced
        profiles_ref = (self.db.collection("profiles")
            .where("tenant_id", "==", Config.TENANT_ID)
            .where("engagement_id", "==", Config.ENGAGEMENT_ID)
            .where("active", "==", True))
            
        profiles = list(profiles_ref.stream())
        total_docs = len(profiles)
        logger.info(f"Target Docs: {total_docs}")
        
        count = 0
        for p in profiles:
            doc_id = p.id
            self.rank_doc_edges(doc_id)
            count += 1
            if count % 10 == 0:
                logger.debug(f"Processed {count}/{total_docs} docs...")
                
        logger.info("Ranking Complete.")

    def rank_doc_edges(self, doc_id: str):
        # 해당 문서의 Active Edge 조회
        edges_ref = (self.db.collection("edges_doc_concept") 
            .where("doc_id", "==", doc_id) 
            .where("active", "==", True) 
            .stream())
            
        edges = []
        for e_snap in edges_ref:
            e_data = e_snap.to_dict()
            e_data["_ref"] = e_snap.reference
            edges.append(e_data)
            
        if not edges: return

        # Score 계산
        for edge in edges:
            edge["rank_score"] = self.calculate_score(edge)
            
        # Sort by Score DESC
        edges.sort(key=lambda x: x["rank_score"], reverse=True)
        
        # Diversity Cap (Type별 제한 등) & Total Cap
        # 여기선 단순 Total Cap 적용 (PER_DOC_CAP)
        top_k_edges = edges[:Config.PER_DOC_CAP]
        
        # Batch Update (Edges)
        batch = self.db.batch()
        batch_cnt = 0
        
        for edge in top_k_edges:
            # Update Score
            batch.update(edge["_ref"], {
                "rank_score": edge["rank_score"],
                "ranker_version": Config.RANKER_VERSION,
                "scored_at": firestore.SERVER_TIMESTAMP
            })
            batch_cnt += 1
            
        # Document Top Concepts Update
        top_concepts = [
            {
                "concept_id": e["concept_id"],
                "score": e["rank_score"],
                "mentions": e.get("mentions_count", 0)
            }
            for e in top_k_edges
        ]
        
        doc_ref = self.db.collection("documents").document(doc_id)
        batch.set(doc_ref, {"top_concepts": top_concepts}, merge=True)
        batch_cnt += 1
        
        if batch_cnt > 0:
            batch.commit()
            
    def run(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            return
            
        self.load_concept_df()
        self.process_edges_per_doc()

if __name__ == "__main__":
    ranker = EdgeRanker()
    ranker.run()
