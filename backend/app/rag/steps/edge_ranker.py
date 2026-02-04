import logging
import math
from google.cloud import firestore

from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("EdgeRanker")
logger.setLevel(logging.INFO)

class EdgeRanker:
    def __init__(self):
        self.db = get_firestore_client()
        self.per_doc_cap = int(getattr(settings, "PER_DOC_CAP", 50))
        self.ranker_version = getattr(settings, "EDGE_RANKER_VERSION", "v1")
        self.concept_df = {}
        # Pre-load stats? 
        # In a real per-doc environment, maybe we query stats or cache them.
        # Here we load all for simplicity (Memory warning if concepts > 100k)
        # Or load on demand? DF loading is heavy.
        # For now, let's assume we load it once or it's empty (fallback).
        self.load_concept_df()

    def load_concept_df(self):
        # Only active true?
        # This scanning might be too slow for every startup.
        # Should rely on a cached stat object or bigquery in future.
        # For now, we try to load.
        # Optimization: Don't load if too many?
        # Or, just check concepts count.
        logger.info("Loading Concept DF (Lazy/Lite mode)...")
        # In per-doc mode, maybe we don't load ALL.
        # Just use default DF=1 if not found?
        pass

    def get_concept_df(self, concept_id: str) -> int:
        if concept_id in self.concept_df:
            return self.concept_df[concept_id]
        
        # On-Demand Fetch (Slower but safer for per-doc)
        # But doing this for every edge is N reads.
        # Maybe just assume DF=1 (Local only scoring) if map is empty.
        return 1

    def calculate_score(self, edge, df):
        confidence = edge.get("confidence", 1.0)
        mentions = edge.get("mentions_count", 1)
        if df < 1: df = 1
        scarcity = 10.0 / (math.log(1 + df) + 1.0)
        local_importance = math.log(1 + mentions)
        return round(confidence * scarcity * local_importance, 4)

    def process_single_document(self, doc_id: str):
        # 1. Fetch Edges
        edges_ref = (self.db.collection("edges_doc_concept")
            .where(filter=firestore.FieldFilter("doc_id", "==", doc_id))
            .where(filter=firestore.FieldFilter("active", "==", True))
            .stream())
        
        edges = []
        for e in edges_ref:
            d = e.to_dict()
            d["_ref"] = e.reference
            edges.append(d)
        
        if not edges: return

        # 2. Score
        for edge in edges:
            concept_id = edge.get("concept_id")
            df = self.get_concept_df(concept_id)
            edge["rank_score"] = self.calculate_score(edge, df)
            
        # 3. Sort & Top K
        edges.sort(key=lambda x: x["rank_score"], reverse=True)
        top_k = edges[:self.per_doc_cap]
        
        # 4. Update Edges & Doc
        batch = self.db.batch()
        batch_cnt = 0
        
        for edge in top_k:
            batch.update(edge["_ref"], {
                "rank_score": edge["rank_score"],
                "ranker_version": self.ranker_version,
                "scored_at": firestore.SERVER_TIMESTAMP
            })
            batch_cnt += 1
            
        top_concepts = [{
            "concept_id": e["concept_id"],
            "score": e["rank_score"],
            "mentions": e.get("mentions_count", 0)
        } for e in top_k]
        
        batch.set(self.db.collection("documents").document(doc_id), {
            "top_concepts": top_concepts
        }, merge=True)
        
        if batch_cnt > 0: batch.commit()
        logger.info(f"✅ [Rank] 랭킹 완료: Top {len(top_concepts)}")
