import logging
import os
from typing import Dict, Any, List, Tuple
from app.services.firestore_repo import FirestoreRepo

# 환경 변수 로드 (일부 설정용)
GRAPH_INIT_MAX_NODES = int(os.getenv("GRAPH_INIT_MAX_NODES", 300))
GRAPH_INIT_MAX_EDGES = int(os.getenv("GRAPH_INIT_MAX_EDGES", 500))

logger = logging.getLogger("GraphQueryService")

class GraphQueryService:
    def __init__(self, repo: FirestoreRepo):
        self.repo = repo
        # PermissionGuard: 실제로는 별도 모듈로 분리해야 하나 운영 최소로 내부에 단순 구현
        # 추후 services.permission_guard import
        
    def _apply_permissions(self, nodes: List[Dict], edges: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        보안 및 상태 필터링
        - Active=False 제외
        - Review Status != Approved 제외
        - Security Level 검사 (여기선 L1만 허용하거나, 사용자 권한 비교)
        - 운영 최소: Active=True만 남기고 Review Status는 API 요청 단계에서 이미 필터링되었다고 가정
          (FirestoreRepo가 기본적으로 Active=True만 가져옴)
        """
        # Node Filter
        valid_node_ids = set()
        filtered_nodes = []
        
        for n in nodes:
            # 문서 노드인 경우 추가 검증? (이미 서빙 인덱스 빌드 시 걸러졌다고 가정)
            filtered_nodes.append(n)
            valid_node_ids.add(n["id"])
            
        # Edge Filter
        filtered_edges = []
        for e in edges:
            if e["source"] in valid_node_ids and e["target"] in valid_node_ids:
                filtered_edges.append(e)
                
        return filtered_nodes, filtered_edges

    def get_overview(self, limit: int = None) -> Dict[str, Any]:
        """초기 그래프 로드 (Overview)"""
        limit = limit or GRAPH_INIT_MAX_NODES
        data = self.repo.get_graph_init(limit_nodes=limit)
        
        # Format Translation (Firestore -> Frontend Graph)
        nodes = []
        edges = [] # init 단계에선 edges 생략 혹은 주요 엣지만?
        
        # Concepts to Nodes
        for c in data.get("concepts", []):
            meta = c.get("meta", {})
            nodes.append({
                "id": c.get("concept_id"),
                "label": meta.get("name", c.get("concept_id")),
                "type": "concept",
                "concept_type": meta.get("type", "OTHERS"),
                "size": c.get("doc_count", 1)  # 시각화 사이즈용
            })

            # Edge 추가 (Concept -> Top Docs)
            # overview에서 엣지를 다 그리면 너무 많음. 상위 몇개만?
            # 운영 최소: 엣지 없이 노드만 보내거나, 아주 강한 엣지만 포함
            # 여기선 생략하고, 노드 클릭 시 expand 권장
            
        # Docs to Nodes
        for d in data.get("docs", []):
            nodes.append({
                "id": d.get("doc_id"),
                "label": d.get("doc_id"), # 제목이 있으면 좋음 (repo가 가져올 때 포함 필요)
                "type": "document",
                "size": d.get("concept_count", 1)
            })
            
        # Permission Filter
        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        
        return {
            "nodes": clean_nodes,
            "edges": clean_edges,
            "stats": {"node_count": len(clean_nodes), "edge_count": len(clean_edges)}
        }

    def expand_neighborhood(self, node_id: str, node_type: str, limit: int = 50) -> Dict[str, Any]:
        """특정 노드 클릭 시 주변 확장"""
        nodes = []
        edges = []
        
        # Add Center Node (Client가 이미 알고 있겠지만 안전하게 포함)
        nodes.append({"id": node_id, "type": node_type, "label": node_id}) # 정보 부족 시 ID로
        
        neighbors_data = None
        if node_type == "document":
            neighbors_data = self.repo.get_doc_neighbors(node_id)
            if neighbors_data:
                # Doc -> Concepts
                concepts = neighbors_data.get("top_concepts", [])[:limit]
                for c in concepts:
                    cid = c.get("concept_id")
                    nodes.append({
                        "id": cid, 
                        "type": "concept", 
                        "label": c.get("name", cid),
                        "concept_type": c.get("type", "OTHERS")
                    })
                    edges.append({
                        "source": node_id,
                        "target": cid,
                        "score": c.get("score", 0),
                        "type": "mentions"
                    })
                    
        elif node_type == "concept":
            neighbors_data = self.repo.get_concept_neighbors(node_id)
            if neighbors_data:
                # Concept -> Docs
                docs = neighbors_data.get("top_docs", [])[:limit]
                for d in docs: # d: {doc_id, score, ...}
                    did = d.get("doc_id")
                    nodes.append({
                        "id": did,
                        "type": "document",
                        "label": did # 제목 조회하려면 추가 쿼리 필요
                    })
                    edges.append({
                        "source": did,  # Mentions direction: Doc -> Concept
                        "target": node_id,
                        "score": d.get("score", 0),
                        "type": "mentions"
                    })
        
        # Permission Filter
        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        
        return {
            "nodes": clean_nodes,
            "edges": clean_edges
        }
