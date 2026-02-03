
import os
import sys
import logging

# Ensure project root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

# --- 1. 환경변수 설정 (Cloud Run과 동일하게!) ---
os.environ["PROJECT_ID"] = "jnu-rise-edu-150"
os.environ["GCP_PROJECT_ID"] = "jnu-rise-edu-150"
os.environ["VERTEX_LOCATION"] = "us-central1"
os.environ["VECTOR_INDEX_ENDPOINT"] = "projects/jnu-rise-edu-150/locations/us-central1/indexEndpoints/4111375242440474624"
# [핵심] 여기서 REAL ID를 사용!
os.environ["VECTOR_DEPLOYED_INDEX_ID"] = "omnihub_knowledge_v1_deplo_1769937290527"

os.environ["LOG_LEVEL"] = "INFO"
os.environ["TENANT_ID"] = "my-tenant"
os.environ["ENGAGEMENT_ID"] = "eng-001"

# --- Import ---
from app.rag.firestore_repo import FirestoreRepo
from app.rag.retriever import Retriever
from app.rag.generator import Generator

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LocalTest")

# --- Mock Auth Context ---
class MockAuthContext:
    def __init__(self):
        self.user_id = "local-tester"
        self.tenant_id = os.environ["TENANT_ID"]
        self.engagement_id = os.environ["ENGAGEMENT_ID"]
        self.roles = ["admin"]

def run_test_search(query: str):
    print("\n" + "="*60)
    print(f"🔎 질문: {query}")
    print("="*60)
    
    # 1. Initialize Components
    auth_ctx = MockAuthContext()
    repo = FirestoreRepo(auth_ctx)
    retriever = Retriever(repo)
    generator = Generator()
    
    # 2. Retrieve
    print(f"📡 Vector Search 시작... (ID: {os.environ['VECTOR_DEPLOYED_INDEX_ID']})")
    try:
        # Note: 현재 Retriever 필터는 None으로 풀려있거나, PENDING을 포함하도록 수정된 상태임
        results = retriever.retrieve(query, top_k=5)
    except Exception as e:
        print(f"❌ 검색 에러: {e}")
        return

    print(f"✅ 검색된 청크 수: {len(results)}")
    
    if not results:
        print("⚠️ 검색 결과가 없습니다. (인덱싱 지연 또는 ID 불일치)")
        return

    for idx, chunk in enumerate(results):
        print(f"\n[문서 {idx+1}] {chunk.title} (Page {chunk.page}, ID: {chunk.doc_id})")
        print(f"내용 요약: {chunk.snippet[:150]}...")
        # print(f"-> GCS Link: {chunk.source_link}")
    
    # 3. Generate Answer
    print("\n🧠 답변 생성 중 (Gemini)...")
    try:
        # Pydantic -> Dict
        chunks_dict = [c.model_dump() for c in results]
        answer = generator.generate(query, chunks_dict)
        
        print("\n" + "-"*60)
        print(f"🤖 답변:\n{answer}")
        print("-"*60)
    except Exception as e:
        print(f"❌ 답변 생성 에러: {e}")

if __name__ == "__main__":
    test_query = "차입자가 P2P 업체에 내는 수수료는 법정 최고금리 계산에 포함되나요?"
    
    if len(sys.argv) > 1:
        test_query = sys.argv[1]
        
    run_test_search(test_query)
