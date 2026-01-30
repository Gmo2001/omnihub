import sys
import os

# 현재 파일의 부모의 부모 폴더(루트)를 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from services.firestore_repo import FirestoreRepo

# 가짜 인증 정보 생성 (테스트용)
class MockAuth:
    tenant_id = "my-tenant" 
    engagement_id = "my-engagement"
    user_id = "debug-user"

# .env 로드 필요 (DB 접속 정보)
from dotenv import load_dotenv
load_dotenv()

repo = FirestoreRepo(MockAuth())

print("=== Document Folder Path Inspection ===")
# 50개 정도 가져와서 folder_path 통계를 봅니다.
docs = repo.list_documents(limit=50)

if not docs:
    print("문서가 하나도 없습니다. tenant_id/engagement_id 설정을 확인하세요.")
else:
    print(f"총 {len(docs)}개 샘플 문서 로드됨.")
    paths = set()
    for d in docs:
        p = d.get('folder_path', '/')
        paths.add(p)
        # print(f"Doc: {d.get('title')} | Path: {p}")
    
    print("\n[발견된 폴더 경로 목록]")
    for p in sorted(list(paths)):
        print(f" - {p}")
        
    print("\n이 경로 중 하나를 복사해서 트리 API에 folder 파라미터로 넣어보세요.")
