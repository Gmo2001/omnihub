import requests
import json
import time

# ✅ 테스트 설정
API_URL = "http://localhost:8000/api/search/rag"
HEADERS = {
    "X-User-Id": "test-user-001",
    "X-Tenant-Id": "my-tenant",
    "X-Engagement-Id": "eng-001",
    "X-User-Roles": "admin"
}

# ✅ 테스트 질문 목록 (최근 업로드된 문서 기반)
TEST_QUESTIONS = [
    "YES FTA 컨설팅 지원금은 얼마인가요?",
    "YES FTA 컨설팅 지원 대상 기업은 누구인가요?"
]

def run_test():
    print("🚀 [RAG QA Test] Starting...")
    print(f"📡 Target URL: {API_URL}")
    print(f"🔑 Headers: {json.dumps(HEADERS, indent=2)}")
    print("-" * 50)

    for i, question in enumerate(TEST_QUESTIONS):
        print(f"\n❓ Question {i+1}: {question}")
        start_time = time.time()
        
        payload = {
            "query": question,
            "top_k": 5
        }
        
        try:
            response = requests.post(API_URL, json=payload, headers=HEADERS)
            response.raise_for_status()
            
            data = response.json()
            elapsed = time.time() - start_time
            
            cid = data.get("conversation_id", "N/A")
            answer = data.get("answer", "No answer provided")
            citations = data.get("citations", [])
            retrieved_count = data.get("retrieved_count", 0)
            
            print(f"⏱️ Time: {elapsed:.2f}s | 🆔 Conv ID: {cid}")
            print(f"💡 Answer:\n{answer}")
            print(f"\n📚 Citations ({retrieved_count} retrieved, {len(citations)} used):")
            
            if retrieved_count == 0:
                print("   ⚠️ 검색된 문서가 없습니다. (벡터 인덱싱 지연 또는 검색 설정 문제일 수 있습니다)")
            elif not citations:
                print("   (No citations used in answer)")
            
            for j, cit in enumerate(citations):
                title = cit.get("title", "Untitled")
                doc_id = cit.get("doc_id", "Unknown")
                page = cit.get("page", "?")
                link = cit.get("source_link", "")
                snippet = cit.get("snippet", "")
                
                print(f"   [{j+1}] {title} (ID: {doc_id}, Page: {page})")
                if link:
                    print(f"       🔗 {link}")
                
        except requests.exceptions.HTTPError as e:
            print(f"❌ API Error: {e}")
            print(f"   Response: {response.text}")
        except Exception as e:
            print(f"❌ Connection Error: {e}")
            
        print("-" * 50)

if __name__ == "__main__":
    run_test()
