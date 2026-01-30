from typing import List, Optional
from google.cloud import aiplatform
from .config import PROJECT_ID, VERTEX_LOCATION, ME_ENDPOINT_NAME, ME_DEPLOYED_INDEX_ID

class VectorSearchClient:
    def __init__(self):
        aiplatform.init(project=PROJECT_ID, location=VERTEX_LOCATION)
        # display_name으로 endpoint 찾기
        eps = aiplatform.MatchingEngineIndexEndpoint.list(filter=f'display_name="{ME_ENDPOINT_NAME}"')
        if not eps:
            raise RuntimeError(f"Matching Engine Endpoint not found: {ME_ENDPOINT_NAME}")
        # Re-instantiate using resource_name to avoid potential uninitialized attributes from list()
        self.endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=eps[0].resource_name)
        if not ME_DEPLOYED_INDEX_ID:
            raise RuntimeError("ME_DEPLOYED_INDEX_ID is empty. Set env var.")

    def find_topk(self, query_embedding: List[float], top_k: int = 8) -> List[str]:
        # find_neighbors 결과에서 datapoint_id 추출
        try:
            resp = self.endpoint.find_neighbors(
                deployed_index_id=ME_DEPLOYED_INDEX_ID,
                queries=[query_embedding],
                num_neighbors=top_k,
            )
            
            # DEBUG: Log response structure
            with open("vector_search_debug.log", "a", encoding="utf-8") as f:
                f.write(f"\n=== Vector Search Call ===\n")
                f.write(f"Query embedding dim: {len(query_embedding)}\n")
                f.write(f"Deployed index ID: {ME_DEPLOYED_INDEX_ID}\n")
                f.write(f"Requested top_k: {top_k}\n")
                f.write(f"Response type: {type(resp)}\n")
                f.write(f"Response length: {len(resp) if resp else 0}\n")
                if resp:
                    f.write(f"First response type: {type(resp[0])}\n")
                    first = resp[0]
                    neighbors = getattr(first, "neighbors", None)
                    f.write(f"Neighbors: {neighbors}\n")
                    f.write(f"Neighbors type: {type(neighbors)}\n")
                    f.write(f"Neighbors count: {len(neighbors) if neighbors else 0}\n")
            
        except Exception as e:
            with open("vector_search_debug.log", "a", encoding="utf-8") as f:
                f.write(f"ERROR in find_neighbors: {e}\n")
            raise
        
        # resp 구조가 리스트/객체 형태로 올 수 있어 방어적으로 파싱
        ids: List[str] = []
        if not resp:
            return ids

        # 일반적으로 resp[0].neighbors에 neighbor.datapoint.datapoint_id 형태가 있음
        first = resp[0]
        neighbors = getattr(first, "neighbors", None)
        if neighbors is None:
            # 문자열로만 올 때 대비
            return ids

        for n in neighbors:
            dp = getattr(n, "datapoint", None)
            if dp is None:
                continue
            did = getattr(dp, "datapoint_id", None)
            if did:
                ids.append(did)
        return ids
