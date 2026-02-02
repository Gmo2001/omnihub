import os
import logging
from typing import Optional, Dict, List, Any
from google.cloud import firestore
from app.common.types import AuthContext

# AuthContext는 순환 참조 방지를 위해 여기서 import 안하고, dict/object로 가정하거나
# TYPE_CHECKING 블록을 사용. 여기선 Any로 받음.

from dotenv import load_dotenv
load_dotenv()

# --- Configurations ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DB)
logger = logging.getLogger("FirestoreRepo")

class FirestoreRepo:
    def __init__(self, auth_ctx: AuthContext):
        """
        auth_ctx: must have tenant_id, engagement_id user_id
        """
        self.tenant_id = auth_ctx.tenant_id
        self.engagement_id = auth_ctx.engagement_id
        self.user_id = auth_ctx.user_id
        self.db = db # Global use

    def _scope_check(self, data: Dict[str, Any]) -> bool:
        """데이터의 Scope가 요청자와 일치하는지 확인 (Double Check)"""
        if not data: return False
        t = data.get("tenant_id")
        e = data.get("engagement_id")
        # 없는 경우는? 레거시 등. 엄격 모드면 False.
        if t != self.tenant_id or e != self.engagement_id:
            return False
        return True

    def _base_query(self, collection_name: str):
        return (db.collection(collection_name)
            .where("tenant_id", "==", self.tenant_id)
            .where("engagement_id", "==", self.engagement_id))

    # --- 1. Documents ---
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        doc_ref = db.collection("documents").document(doc_id).get()
        if not doc_ref.exists:
            return None
        
        data = doc_ref.to_dict()
        if not self._scope_check(data):
            logger.warning(f"Scope Mismatch Access Attempt: {doc_id} by {self.user_id}")
            # Raise Forbidden? Or just return None
            return None
            
        return data

    def list_documents(self, 
                       folder_path: str = None, 
                       limit: int = 50, 
                       cursor: Any = None,
                       filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        
        query = self._base_query("documents")
        
        # Filter: Active is default True unless specified
        # filters가 None이면 기본 active=True 포함?
        # 여기선 명시적으로 active=True를 기본으로
        query = query.where("active", "==", True)
        
        if folder_path:
            query = query.where("folder_path", "==", folder_path)
            
        if filters:
            for k, v in filters.items():
                if v is not None:
                    query = query.where(k, "==", v)
                    
        # OrderBy (운영 최소: 일단 updated_at DESC나 id)
        # 하지만 index가 없으면 에러남. 단순 limit만
        query = query.limit(limit)
        
        if cursor:
            query = query.start_after(cursor)
            
        docs = query.stream()
        results = []
        for d in docs:
            data = d.to_dict()
            results.append(data) # id 포함?
            
        return results

    def update_doc_status(self, doc_id: str, new_status: str, reason: str = None, updates: Dict[str, Any] = None):
        """
        Update document status and related workflow fields.
        Uses a transaction (simulated or explicit) to ensure consistency.
        """
        # 1. Validation (Exist & Scope)
        origin = self.get_document(doc_id)
        if not origin:
            raise ValueError(f"Document {doc_id} not found or access denied")
            
        # 2. Prepare Payload
        payload = {
            "review_status": new_status,
            "status_updated_at": firestore.SERVER_TIMESTAMP,
            "status_updated_by": self.user_id,
            "last_review_by": self.user_id,
            "last_review_reason": reason
        }
        
        if updates:
            payload.update(updates)

        # 3. Transaction Execution
        # Firestore Transaction을 사용하여 동시성 제어 권장
        # e.g., @firestore.transactional def update_in_txn(txn, ...): ...
        
        # 운영 최소: Atomic Merge Update
        db.collection("documents").document(doc_id).set(payload, merge=True)
        
        logger.info(f"Doc {doc_id} status updated to {new_status} by {self.user_id}")

    # --- 2. Cards ---
    def get_card(self, doc_id: str) -> Optional[Dict[str, Any]]:
        # Card 역시 Scope Check가 필요하나, cards 컬렉션에도 tenant_id를 넣었으므로 가능
        # 만약 안넣었다면 profile/document를 통해 간접 확인해야 함.
        # B단계 스크립트에서 card에도 tenant_id 넣었음.
        
        card_ref = db.collection("cards").document(doc_id).get()
        if not card_ref.exists:
            return None
            
        data = card_ref.to_dict()
        if not self._scope_check(data):
            return None
        return data

    # --- 3. Graph ---
    def get_graph_init(self, limit_nodes: int = 500) -> Dict[str, List[Any]]:
        """
        초기 그래프 로딩: 상위 중요 문서/개념들
        """
        # Top Concepts
        cq = (self._base_query("graph_serving_concepts")
            .limit(limit_nodes).stream()) # rank_score sort needed ideally
            
        concepts = [c.to_dict() for c in cq]
        
        # Top Docs (Central Nodes)
        dq = (self._base_query("graph_serving_docs")
            .limit(limit_nodes).stream())
            
        docs = [d.to_dict() for d in dq]
        
        return {"concepts": concepts, "docs": docs}

    def get_doc_neighbors(self, doc_id: str) -> Optional[Dict[str, Any]]:
        ref = db.collection("graph_serving_docs").document(doc_id).get()
        if not ref.exists: return None
        data = ref.to_dict()
        if not self._scope_check(data): return None
        return data

    def get_concept_neighbors(self, concept_id: str) -> Optional[Dict[str, Any]]:
        ref = db.collection("graph_serving_concepts").document(concept_id).get()
        if not ref.exists: return None
        data = ref.to_dict()
        if not self._scope_check(data): return None
        return data

    # --- 4. Tree ---
    def get_tree_children(self, folder_path: str = "/") -> List[Dict[str, Any]]:
        # Tree Index 컬렉션 사용 가정 (tree_index/{hash})
        # document list 쿼리로 대체 가능하지만 성능 위해 별도 인덱스가 좋음
        # 여기서는 documents query 활용 (운영 최소)
        
        query = (self._base_query("documents")
            .where("active", "==", True)
            .where("folder_path", "==", folder_path)
            .limit(100)
            .stream())
            
        return [d.to_dict() for d in query]
