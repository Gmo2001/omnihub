import sys
import os

# 현재 파일의 부모의 부모 폴더(루트)를 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from services.firestore_repo import FirestoreRepo # 이제 정상 작동합니다!

# 가짜 인증 정보 생성
class MockAuth:
    tenant_id = "my-tenant"
    engagement_id = "my-engagement"
    user_id = "test-user"

auth = MockAuth()
repo = FirestoreRepo(auth)

# 1. 문서 목록 불러오기 테스트
docs = repo.list_documents(limit=5)
print(f"가져온 문서 개수: {len(docs)}")

# 2. 첫 번째 문서 내용 살짝 보기
if docs:
    print(f"첫 번째 문서 제목: {docs[0].get('title')}")