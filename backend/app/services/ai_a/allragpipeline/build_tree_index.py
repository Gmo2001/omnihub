import os
import argparse
import hashlib
import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.cloud import firestore
from app.services.ai_a.allragpipeline.common.enums import SecurityLevel, ReviewStatus

# 로컬 환경 변수 로드
load_dotenv()

# Logger
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TreeIndexBuilder")

class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")
    TREE_INDEX_VERSION = os.getenv("TREE_INDEX_VERSION", "v1")
    FOLDER_DOC_CAP = int(os.getenv("TREE_FOLDER_DOC_CAP", 500))
    DOCS_PER_FOLDER_CAP = int(os.getenv("TREE_DOCS_PER_FOLDER_CAP", 300))
    LOOKBACK_DAYS = int(os.getenv("INCREMENTAL_LOOKBACK_DAYS", 7))

class TreeIndexBuilder:
    def __init__(self):
        self.db = firestore.Client(project=Config.PROJECT_ID, database=Config.FIRESTORE_DB)
        # 로컬 캐시 (배치 처리를 위함)
        # Key: folder_key, Value: {docs: [], folders: set()}
        self.tree_cache = {} 

    def _get_folder_key(self, tenant_id, engagement_id, folder_path):
        """
        Generate safe Firestore Document ID for a folder
        Format: {tenant}__{engagement}__{hash(path)}
        """
        # Normalize path
        normalized_path = folder_path.strip()
        if not normalized_path.startswith("/"):
            normalized_path = "/" + normalized_path
        if not normalized_path.endswith("/"):
            normalized_path = normalized_path + "/"
            
        path_hash = hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()[:16]
        return f"{tenant_id}__{engagement_id}__{path_hash}", normalized_path

    def _load_profiles(self, tenant_id, engagement_id, mode, doc_id=None):
        """Fetch profiles from Firestore"""
        col_ref = self.db.collection("profiles")
        
        if doc_id:
            logger.info(f"Fetching single profile: {doc_id}")
            doc = col_ref.document(doc_id).get()
            return [doc] if doc.exists else []
            
        query = (col_ref.where(filter=firestore.FieldFilter("tenant_id", "==", tenant_id))
                       .where(filter=firestore.FieldFilter("engagement_id", "==", engagement_id)))
                       
        if mode == "incremental":
            # 최근 변경분만 조회 (운영 최적화)
            cutoff = datetime.now() - timedelta(days=Config.LOOKBACK_DAYS)
            # 복합 인덱스 필요 가능성 있음 (tenant + engagement + modified_time)
            # 여기선 간단히 앱 레벨 필터링 or 전체 스캔
            # query = query.where("modified_time", ">=", cutoff)
            pass 

        logger.info(f"Fetching profiles for {tenant_id}/{engagement_id} (Mode: {mode})")
        # 리스트로 반환 (메모리 주의)
        return list(query.get())

    def _add_to_cache(self, tenant_id, engagement_id, profile_data):
        """
        Parse profile and add to local tree cache
        """
        doc_id = profile_data.get("doc_id")
        title = profile_data.get("title", "Untitled")
        folder_path = profile_data.get("folder_path", "/")
        
        # Normalize
        if not folder_path.startswith("/"): folder_path = "/" + folder_path
        if not folder_path.endswith("/"): folder_path += "/"
        
        # 1. 자신을 포함하는 폴더(Parent) 처리
        folder_key, normalized_path = self._get_folder_key(tenant_id, engagement_id, folder_path)
        
        if folder_key not in self.tree_cache:
            self.tree_cache[folder_key] = {
                "tenant_id": tenant_id,
                "engagement_id": engagement_id,
                "folder_path": normalized_path,
                "children_docs": [],
                "children_folders": set(),
                "doc_ids": set() # 중복 방지용
            }
            
        # Add Doc to Folder
        if doc_id not in self.tree_cache[folder_key]["doc_ids"]:
            doc_info = {
                "doc_id": doc_id,
                "title": title,
                "modified_time": profile_data.get("modified_time"),
                "review_status": ReviewStatus.normalize(profile_data.get("review_status")).value,
                "security_level": SecurityLevel.normalize(profile_data.get("security_level")).value,
                # "content_type": ... (Minimal contract excludes this, but acceptable)
            }
            self.tree_cache[folder_key]["children_docs"].append(doc_info)
            self.tree_cache[folder_key]["doc_ids"].add(doc_id)

        # 2. 상위 폴더 구조 만들기 (Recurisve or Loop)
        # 예: /A/B/C/ -> A의 자식 B, B의 자식 C
        # Root(/) -> A -> B -> C
        
        parts = [p for p in normalized_path.split("/") if p]
        # parts: ['A', 'B', 'C']
        
        current_path = "/"
        
        # Root 등록
        root_key, root_path = self._get_folder_key(tenant_id, engagement_id, "/")
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
            
            # Ensure Child Folder Exists in Cache
            if child_key not in self.tree_cache:
                self.tree_cache[child_key] = {
                    "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": child_path,
                    "children_docs": [], "children_folders": set(), "doc_ids": set()
                }
            
            # Add Child to Parent's children_folders
            # (Set of tuple for dedup)
            self.tree_cache[parent_key]["children_folders"].add((part, child_path))
            
            # Move down
            parent_key = child_key
            parent_path = child_path

    def flush_to_firestore(self):
        """
        Write cache to Firestore
        """
        BATCH_SIZE = 400
        batch = self.db.batch()
        count = 0
        total_updates = 0
        
        logger.info(f"Flushing {len(self.tree_cache)} folders to Firestore...")
        
        for key, data in self.tree_cache.items():
            ref = self.db.collection("tree_index").document(key)
            
            # List 변환 및 정렬
            c_docs = sorted(data["children_docs"], key=lambda x: x.get("title", ""))
            
            # Folder Set -> List of Dict
            c_folders = []
            for name, path in sorted(list(data["children_folders"])):
                c_folders.append({
                    "name": name,
                    "path": path,
                    "updated_at": datetime.now().isoformat()
                })
            
            # CAP 적용 (운영 최소)
            has_more_docs = False
            if len(c_docs) > Config.DOCS_PER_FOLDER_CAP:
                c_docs = c_docs[:Config.DOCS_PER_FOLDER_CAP]
                has_more_docs = True
                
            payload = {
                "tenant_id": data["tenant_id"],
                "engagement_id": data["engagement_id"],
                "folder_path": data["folder_path"],
                "version": Config.TREE_INDEX_VERSION,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "children_folders": c_folders,
                "children_docs": c_docs,
                "counts": {
                    "folders": len(c_folders),
                    "docs": len(data["doc_ids"]) # 전체 카운트 (CAP 적용 전)
                },
                "has_more_docs": has_more_docs
            }
            
            batch.set(ref, payload, merge=True)
            count += 1
            
            if count >= BATCH_SIZE:
                batch.commit()
                total_updates += count
                count = 0
                batch = self.db.batch()
                
        if count > 0:
            batch.commit()
            total_updates += count
            
        logger.info(f"Completed. Updated {total_updates} folder documents.")

    def run(self, tenant_id, engagement_id, mode="incremental", doc_id=None):
        # 1. Load Profiles
        docs_snaps = self._load_profiles(tenant_id, engagement_id, mode, doc_id)
        if not docs_snaps:
            logger.info("No profiles found to process.")
            return

        # 2. Build Memory Tree
        for snap in docs_snaps:
            self._add_to_cache(tenant_id, engagement_id, snap.to_dict())
            
        # 3. Flush
        self.flush_to_firestore()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant_id", required=True)
    parser.add_argument("--engagement_id", required=True)
    parser.add_argument("--doc_id", help="Single doc update")
    parser.add_argument("--mode", default="incremental", choices=["full", "incremental"])
    
    args = parser.parse_args()
    
    builder = TreeIndexBuilder()
    builder.run(args.tenant_id, args.engagement_id, args.mode, args.doc_id)
