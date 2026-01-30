import sys
import os

# 현재 파일(utilly/test_graph.py)의 부모 폴더의 부모 폴더(루트)를 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from services.firestore_repo import FirestoreRepo
from services.graph_query_service import GraphQueryService

# 1. 가짜 인증 및 리포지토리 준비
class MockAuth:
    tenant_id = "my-tenant"
    engagement_id = "my-engagement"
    user_id = "test-user"

repo = FirestoreRepo(MockAuth())
service = GraphQueryService(repo)

# 2. 초기 그래프 오버뷰 데이터 가져오기 테스트
overview = service.get_overview(limit=10) #
print(f"생성된 노드 개수: {len(overview['nodes'])}")
if overview['nodes']:
    print(f"첫 번째 노드 샘플: {overview['nodes'][0]}")

# 3. 특정 문서 클릭 시 '이웃 노드 확장' 테스트
# doc_id는 실제 Firestore에 있는 ID 중 하나를 사용해 보세요.
sample_doc_id = "08ef43fabee6b8d058f14bd8d9f3ba388035c18b8f05a431db4ee2997785aa40"
neighbors = service.expand_neighborhood(sample_doc_id, "document") #
print(f"확장된 이웃 데이터: {len(neighbors['nodes'])} nodes, {len(neighbors['edges'])} edges")