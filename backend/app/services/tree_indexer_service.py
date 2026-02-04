
import os
import hashlib
import logging
from typing import Dict, Any, List
from datetime import datetime
from google.cloud import firestore
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import SecurityLevel, ReviewStatus

logger = logging.getLogger("TreeIndexerService")
logger.setLevel(logging.INFO)

class TreeIndexerService:
    def __init__(self):
        self.db = get_firestore_client()
        self.tree_cache = {}
        
        # Config
        self.folder_doc_cap = int(getattr(settings, "TREE_FOLDER_DOC_CAP", 500))
        self.docs_per_folder_cap = int(getattr(settings, "TREE_DOCS_PER_FOLDER_CAP", 300))
        self.version = getattr(settings, "TREE_INDEX_VERSION", "v1")

    def _get_folder_key(self, tenant_id: str, engagement_id: str, folder_path: str):
        """
        Generate Firestore Document ID for a folder
        Format: {tenant}__{engagement}__{hash(path)}
        """
        normalized_path = folder_path.strip()
        if not normalized_path.startswith("/"): normalized_path = "/" + normalized_path
        if not normalized_path.endswith("/"): normalized_path = normalized_path + "/"
            
        path_hash = hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()[:16]
        return f"{tenant_id}__{engagement_id}__{path_hash}", normalized_path

    def _add_to_cache(self, tenant_id: str, engagement_id: str, profile_data: Dict[str, Any]):
        """
        문서 정보를 바탕으로 트리 구조(파일, 폴더)를 메모리 캐시에 구성
        """
        doc_id = profile_data.get("doc_id")
        title = profile_data.get("title", "Untitled")
        folder_path = profile_data.get("folder_path", "/")
        
        # Normalize
        if not folder_path.startswith("/"): folder_path = "/" + folder_path
        if not folder_path.endswith("/"): folder_path += "/"
        
        # 1. 문서가 속한 폴더(Parent) 처리
        folder_key, normalized_path = self._get_folder_key(tenant_id, engagement_id, folder_path)
        
        if folder_key not in self.tree_cache:
            self.tree_cache[folder_key] = {
                "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": normalized_path,
                "children_docs": [], "children_folders": set(), "doc_ids": set()
            }
            
        # Add Doc to Folder Cache
        if doc_id and doc_id not in self.tree_cache[folder_key]["doc_ids"]:
            doc_info = {
                "doc_id": doc_id,
                "title": title,
                "modified_time": profile_data.get("modified_time"),
                "review_status": profile_data.get("review_status", ReviewStatus.PENDING.value),
                "security_level": profile_data.get("security_level", SecurityLevel.LOW.value),
            }
            self.tree_cache[folder_key]["children_docs"].append(doc_info)
            self.tree_cache[folder_key]["doc_ids"].add(doc_id)

        # 2. 상위 폴더 계층 구조 만들기 (Recursive Path Generation)
        # 예: /A/B/C/ -> Root에게 A 등록, A에게 B 등록, B에게 C 등록
        parts = [p for p in normalized_path.split("/") if p]
        
        current_path = "/"
        # Root 등록
        root_key, _ = self._get_folder_key(tenant_id, engagement_id, "/")
        if root_key not in self.tree_cache:
            self.tree_cache[root_key] = {
                "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": "/",
                "children_docs": [], "children_folders": set(), "doc_ids": set()
            }
            
        parent_key = root_key
        parent_path = "/"
        
        for part in parts:
            child_path = parent_path + part + "/"
            child_key, _ = self._get_folder_key(tenant_id, engagement_id, child_path)
            
            # Ensure Child Folder Exists
            if child_key not in self.tree_cache:
                self.tree_cache[child_key] = {
                    "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": child_path,
                    "children_docs": [], "children_folders": set(), "doc_ids": set()
                }
            
            # Parent에게 Child 폴더 등록
            self.tree_cache[parent_key]["children_folders"].add((part, child_path))
            
            # Move down
            parent_key = child_key
            parent_path = child_path

    def flush_to_firestore(self):
        """메모리 캐시 내용을 Firestore에 일괄 저장"""
        batch = self.db.batch()
        count = 0
        total_updates = 0
        
        for key, data in self.tree_cache.items():
            ref = self.db.collection("tree_index").document(key)
            
            # Docs 정렬 (이름순)
            c_docs = sorted(data["children_docs"], key=lambda x: x.get("title", ""))[:self.docs_per_folder_cap]
            
            # Folders 정렬
            c_folders = []
            for name, path in sorted(list(data["children_folders"])):
                c_folders.append({"name": name, "path": path, "updated_at": datetime.now().isoformat()})
                
            payload = {
                "tenant_id": data["tenant_id"],
                "engagement_id": data["engagement_id"],
                "folder_path": data["folder_path"],
                "version": self.version,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "children_folders": c_folders,
                "children_docs": c_docs, # Limit applied
                "has_more_docs": len(data["children_docs"]) > self.docs_per_folder_cap
            }
            
            batch.set(ref, payload, merge=True)
            count += 1
            if count >= 400:
                batch.commit()
                total_updates += count
                count = 0
                batch = self.db.batch()
                
        if count > 0:
            batch.commit()
            total_updates += count
            
        logger.info(f"✅ [TreeIndex] Updated {total_updates} folder nodes.")
        self.tree_cache.clear() # Reset cache

    def process_single_doc(self, profile_data: Dict[str, Any]):
        """단일 문서 변경 시 해당 문서의 트리 경로만 부분 업데이트"""
        if not profile_data: return
        t = profile_data.get("tenant_id")
        e = profile_data.get("engagement_id")
        
        self._add_to_cache(t, e, profile_data)
        self.flush_to_firestore() # 단건 즉시 반영

    def refresh_all(self, tenant_id: str, engagement_id: str):
        """전체 재구성 (Batch Job용)"""
        logger.info(f"Refreshing Tree Index for {tenant_id}/{engagement_id}")
        query = (self.db.collection("profiles")
                 .where("tenant_id", "==", tenant_id)
                 .where("engagement_id", "==", engagement_id)
                 .stream())
                 
        for doc in query:
            self._add_to_cache(tenant_id, engagement_id, doc.to_dict())
            
        self.flush_to_firestore()
