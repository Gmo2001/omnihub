import os
import logging
from typing import Optional, Dict, List, Any
from google.cloud import firestore
from app.services.ai_a.allragpipeline.common.types import AuthContext

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

    # --- 1. Documents (Adapter Pattern: Files -> AI Schema) ---
    def _adapt_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [Action 2] Backend 'files' Schema (CamelCase) -> AI Pipeline Schema (snake_case)
        Acts as an anti-corruption layer.
        """
        if not data: return {}
        
        # Owners parsing
        owner_name = "unknown"
        owners = data.get("owners", [])
        if owners and isinstance(owners, list):
            first_owner = owners[0]
            if isinstance(first_owner, str):
                owner_name = first_owner
            elif isinstance(first_owner, dict):
                owner_name = first_owner.get("displayName", "unknown")

        return {
            # Identity
            "doc_id": data.get("fileId"),
            "title": data.get("name"),
            
            # Content Access
            "gcs_uri": data.get("gcsUri"),
            "mime_type": data.get("mimeType"),
            
            # Metadata
            "created_at": data.get("createdAt"),
            "updated_at": data.get("updatedAt"),
            "owner": owner_name,
            
            # Context / Security
            "tenant_id": data.get("tenant_id", self.tenant_id),
            "engagement_id": data.get("engagement_id", "default"), 
            "security_level": data.get("securityLevel", "unclassified"),
            
            # Status Mapping
            "pipeline_status": data.get("aiStatus", "pending"),
            "review_status": data.get("reviewStatus", "unreviewed"),
            
            # Raw Data
            "_raw": data
        }

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        # [Direct Access] Query 'files' collection
        doc_ref = db.collection("files").document(doc_id).get()
        
        if not doc_ref.exists:
            return None
        
        return self._adapt_schema(doc_ref.to_dict())

    def list_documents(self, 
                       folder_path: str = None, # Deprecated in flat files model, kept for signature
                       limit: int = 50, 
                       cursor: Any = None,
                       filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        
        # [Direct Access] List from 'files'
        query = self._base_query("files")
        
        if filters:
            key_map = {"review_status": "reviewStatus", "security_level": "securityLevel"}
            for k, v in filters.items():
                backend_key = key_map.get(k, k)
                if v is not None:
                    query = query.where(backend_key, "==", v)
                    
        query = query.limit(limit)
        
        if cursor:
            query = query.start_after(cursor)
            
        docs = query.stream()
        return [self._adapt_schema(d.to_dict()) for d in docs]

    def update_doc_status(self, doc_id: str, new_status: str, reason: str = None, updates: Dict[str, Any] = None):
        payload = {
            "reviewStatus": new_status,
            "lastModifiedBy": self.user_id,
            "statusUpdatedAt": firestore.SERVER_TIMESTAMP
        }
        if reason:
            payload["reviewStatusReason"] = reason
        if updates:
             # Add specific mappings if needed
             pass

        db.collection("files").document(doc_id).set(payload, merge=True)
        logger.info(f"File {doc_id} status updated to {new_status} by {self.user_id}")

    # --- 2. Cards ---
    def get_card(self, doc_id: str) -> Optional[Dict[str, Any]]:
        # Cards might still stay in 'cards' or move to 'ai_results' later. 
        # For now, keep as is or adapt if Action 2.5 is engaged.
        card_ref = db.collection("cards").document(doc_id).get()
        if not card_ref.exists:
            return None
        data = card_ref.to_dict()
        if not self._scope_check(data): return None
        return data

    # --- 3. Graph ---
    def get_graph_init(self, limit_nodes: int = 500) -> Dict[str, List[Any]]:
        cq = (self._base_query("graph_serving_concepts").limit(limit_nodes).stream())
        concepts = [c.to_dict() for c in cq]
        
        dq = (self._base_query("graph_serving_docs").limit(limit_nodes).stream())
        docs = [d.to_dict() for d in dq]
        
        return {"concepts": concepts, "docs": docs}

    def get_doc_neighbors(self, doc_id: str) -> Optional[Dict[str, Any]]:
        ref = db.collection("graph_serving_docs").document(doc_id).get()
        if not ref.exists: return None
        return ref.to_dict()

    def get_concept_neighbors(self, concept_id: str) -> Optional[Dict[str, Any]]:
        ref = db.collection("graph_serving_concepts").document(concept_id).get()
        if not ref.exists: return None
        return ref.to_dict()

    # --- 4. Tree ---
    def get_tree_children(self, folder_path: str = "/") -> List[Dict[str, Any]]:
        # Simulate tree using files? 
        # For now, return empty or implement basic query on 'files' if virtual_path exists.
        return []
