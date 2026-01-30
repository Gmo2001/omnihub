import requests
import json

# 1. 환경 설정
BASE_URL = "http://localhost:8000"
RAG_URL = f"{BASE_URL}/api/search/rag"

# 테스트용 컨텍스트 (파이프라인 실행 시 사용한 값과 동일해야 함)
HEADERS = {
    "X-User-Id": "test_admin",
    "X-Tenant-Id": "my-tenant",
    "X-Engagement-Id": "my-engagement",
    "Content-Type": "application/json"
}

PAYLOAD = {
    "query": "외부감사법(외감법) 개정의 주요 내용과 감사인의 책임에 대해 설명해줘.",
    "tenant_id": "my-tenant",
    "engagement_id": "my-engagement"
}

def run_integration_test():
    print("🚀 [1단계] RAG 통합 검색 및 답변 테스트 시작...")
    try:
        # 한글 처리를 위해 json.dumps 사용
        response = requests.post(RAG_URL, headers=HEADERS, json=PAYLOAD)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ RAG 질의 성공!")
            print(f"⏱️ 소요 시간: {result.get('meta', {}).get('latency_ms', 0) / 1000:.2f}초")
            print("-" * 50)
            print(f"🤖 Gemini의 답변:\n{result.get('answer')}")
            print("-" * 50)
            
            citations = result.get('citations', [])
            print(f"📚 참조된 문서 수: {len(citations)}개")
            for idx, cite in enumerate(citations[:3], 1):
                print(f"   [{idx}] {cite.get('title')} (Page: {cite.get('page')})")
        else:
            print(f"❌ RAG 질의 실패 (상태 코드: {response.status_code})")
            print(response.text)

    except Exception as e:
        print(f"🚨 에러 발생: {e}")

    print("\n🛡️ [2단계] 보안 권한(PermissionGuard) 작동 테스트...")
    # 잘못된 테넌트 ID로 요청 시 차단되는지 확인
    bad_headers = HEADERS.copy()
    bad_headers["X-Tenant-Id"] = "wrong-tenant"
    
    response_sec = requests.post(RAG_URL, headers=bad_headers, json=PAYLOAD)
    if response_sec.status_code == 403 or response_sec.status_code == 404:
        print("✅ 보안 가드 정상 작동: 권한 없는 테넌트 접근 차단 성공")
    else:
        print(f"⚠️ 보안 취약점 발견: 차단되어야 할 요청이 통과됨 (Status: {response_sec.status_code})")

if __name__ == "__main__":
    run_integration_test()