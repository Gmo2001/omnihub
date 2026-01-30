import sys, os
from dotenv import load_dotenv
load_dotenv()

# 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from services.firestore_repo import FirestoreRepo
from services.retriever import Retriever
# test_retriever_direct.py 상단에 추가
from google.cloud import aiplatform

endpoint = aiplatform.MatchingEngineIndexEndpoint(os.getenv("VECTOR_INDEX_ENDPOINT"))
print("=== 현재 엔드포인트에 배포된 인덱스 목록 ===")
for deployed_index in endpoint.deployed_indexes:
    print(f"- ID: {deployed_index.id} (Display: {deployed_index.display_name})")

# 1. 인증 정보 모킹 (반드시 실제 데이터가 있는 테넌트 ID 입력)
class MockAuth:
    tenant_id = "my-tenant"
    engagement_id = "my-engagement"
    user_id = "junyoung"

repo = FirestoreRepo(MockAuth())
retriever = Retriever(repo)

# 2. 검색 테스트
query = "예금보험제도"
print(f"🔍 검색 쿼리: {query}")

results = retriever.retrieve(query=query, top_k=3)

# 3. 결과 출력
if not results:
    print("❌ 검색 결과가 없습니다. (필터 조건 또는 인덱스 상태 확인 필요)")
else:
    for i, res in enumerate(results):
        print(f"[{i+1}] Score: {res['score']:.4f} | Title: {res['doc_title']}")
        print(f"   ID: {res['chunk_id']}")
        print(f"   Snippet: {res['text'][:50]}...")