import sys, os
from dotenv import load_dotenv
load_dotenv()

# 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from services.firestore_repo import FirestoreRepo
from services.retriever import Retriever
from google.cloud import aiplatform

# 1. 환경 변수 체크
print("--- ENV CHECK ---")
print(f"PROJECT_ID: {os.getenv('GCP_PROJECT_ID')}")
print(f"ENDPOINT: {os.getenv('VECTOR_INDEX_ENDPOINT')}")
print(f"DEPLOYED_ID: {os.getenv('VECTOR_DEPLOYED_INDEX_ID')}")

# 2. Retriever 초기화
class MockAuth:
    tenant_id = "my-tenant"
    engagement_id = "my-engagement"
    user_id = "junyoung"

repo = FirestoreRepo(MockAuth())
retriever = Retriever(repo)

# 3. 임베딩 생성 & Raw Neighbors 조회 (필터 없이)
query = "예금보험제도"
vec = retriever._embed_query(query)
print(f"\n--- Embed result: dim={len(vec)} ---")

print("\n--- RAW FIND NEIGHBORS (No Filter) ---")
try:
    neighbors = retriever.idx_client.find_neighbors(
        deployed_index_id=os.getenv("VECTOR_DEPLOYED_INDEX_ID"),
        queries=[vec],
        num_neighbors=5,
        # filter=[] # 완전 제거
    )
    print(f"TYPE: {type(neighbors)}")
    print(f"RAW: {neighbors}")
    
    if neighbors and len(neighbors) > 0:
        candidates = neighbors[0]
        print(f"Candidates Count: {len(candidates)}")
        for x in candidates:
             print(f" - ID: {x.id}, Dist: {x.distance}")
    else:
        print("No neighbors found even without filter.")

except Exception as e:
    print(f"Find Neighbors Error: {e}")
