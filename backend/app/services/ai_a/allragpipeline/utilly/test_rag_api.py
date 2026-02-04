import requests
import json
import time

# 1. 설정 정보 (성공한 로그 기준 ID 업데이트)
URL = "http://localhost:8000/api/search/rag"
HEADERS = {
    "X-User-Id": "junyoung",
    "X-Tenant-Id": "my-tenant",
    "X-Engagement-Id": "eng-001",  # 'my-engagement'에서 'eng-001'로 수정
    "Content-Type": "application/json"
}

# 2. 신규 파일(세무/복지/자영업) 중심 성능 검증 질문 리스트
QUESTIONS = [
    "광주지역 자영업자의 재무 건전성이 취약한 주요 이유와 외부자금 조달 특징은?",
    "국내 자영업의 폐업률에 영향을 미치는 경기적 요인과 비용적 요인은 무엇인가요?",
    "기본소득과 안심소득(음의소득세)의 차이점과 안심소득의 급여 산정 방식은?",
    "자영업자가 국민연금 사각지대에 놓이게 되는 원인과 정부의 보험료 지원 방안은?",
    "소득세 과세단위를 개인에서 부부/가족 단위로 변경하자는 논의가 나오는 배경은?",
    "광주지역에서 건설업 및 부동산 임대업 자영업체가 크게 증가한 이유는?",
    "핀란드 기본소득 실험 결과가 근로의욕에 미친 영향에 대한 시사점은?",
    "안심소득 도입 시 자영업자 가구에 대해 해결해야 할 주요 과제는?",
    "국민연금 가입자 중 '납부예외자'와 '장기체납자'의 비중 및 특징은?",
    "독일이 채택하고 있는 '선택적 2분2승제' 과세 방식의 특징은?"
]

def run_rag_test():
    print(f"\n{'='*70}")
    print(f"🔍 Omnihub RAG [세무/복지 신규 데이터] 성능 검증 시작")
    print(f"{'='*70}")

    success_count = 0
    
    for i, query in enumerate(QUESTIONS, 1):
        print(f"\n[Test {i}/10] 질문: {query}")
        
        # 페이로드에 필수 정보 포함
        data = {
            "query": query,
            "tenant_id": HEADERS["X-Tenant-Id"],
            "engagement_id": HEADERS["X-Engagement-Id"],
            "top_k": 5  # 더 정확한 답변을 위해 참조 범위를 넓힘
        }

        try:
            start_time = time.time()
            # 한글 깨짐 방지를 위해 json.dumps 및 인코딩 처리
            response = requests.post(URL, headers=HEADERS, data=json.dumps(data).encode('utf-8'))
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get("answer", "답변 없음")
                meta = result.get("meta", {})
                retrieved = meta.get("retrieved_count", 0)
                
                print(f"✅ 응답 완료 ({latency:.2f}ms) | 검색된 문서 조각: {retrieved}개")
                print(f"🤖 AI 답변 요약: {answer[:300]}...")
                
                # 출처 출력 (첫 번째 출처만 예시로 출력)
                citations = result.get("citations", [])
                if citations:
                    print(f"📚 주요 출처: {citations[0].get('title')} (Page {citations[0].get('page')})")
                
                if "확인할 수 없습니다" not in answer and "불분명" not in answer:
                    success_count += 1
            else:
                print(f"❌ API 에러: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"⚠️ 실행 중 오류 발생: {e}")
        
        print("-" * 50)
        time.sleep(1) # API 부하 방지

    print(f"\n{'='*70}")
    print(f"📊 최종 테스트 결과 요약")
    print(f"- 총 질문 수: {len(QUESTIONS)}")
    print(f"- 성공적인 응답(유효 답변): {success_count}")
    print(f"- 사용된 테넌트: {HEADERS['X-Tenant-Id']} / {HEADERS['X-Engagement-Id']}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    run_rag_test()