import requests
import json
import sys

def test_rag_qa(query: str):
    url = "http://localhost:8000/api/search/rag"
    payload = {
        "query": query,
        "tenant_id": "my-tenant",
        "engagement_id": "eng-001",
        "top_k": 3
    }
    
    print(f"🤔 질문: {query}")
    print(f"📡 요청 보내는 중... ({url})")
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        print("\n✨ 답변:")
        print("========================================")
        print(result["answer"])
        print("========================================")
        
        print("\n📚 참고 문서 (Evidence):")
        for idx, ev in enumerate(result.get("evidence", [])):
            print(f"[{idx+1}] {ev.get('title')} (Page {ev.get('page')})")
            print(f"    Link: {ev.get('source_link')}")
            print(f"    Snippet: {ev.get('snippet')[:100]}...")
            print("-" * 40)
            
    except requests.exceptions.HTTPError as e:
        print(f"❌ API 오류: {e}")
        print(response.text)
    except Exception as e:
        print(f"❌ 연결 실패: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_rag_qa.py \"질문 내용\"")
        # Default test question
        default_q = "가맹점 업무제휴 계약에서 갑이 을에게 제공하는 혜택은 뭐야?"
        print(f"No question provided. Using default: '{default_q}'")
        test_rag_qa(default_q)
    else:
        test_rag_qa(sys.argv[1])
