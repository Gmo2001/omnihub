import sys, os
from dotenv import load_dotenv
load_dotenv()

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from services.generator import Generator

# 1. 가짜 검색 결과(Mock Chunks) 준비
mock_chunks = [
    {
        "doc_title": "FDIC 예금자 보호 제도 안내",
        "page": 1,
        "text": "예금보험공사는 금융기관이 파산할 경우 1인당 최고 5천만 원까지 예금을 보호합니다."
    },
    {
        "doc_title": "2026 회계 감사 리스크 보고서",
        "page": 12,
        "text": "외화 예금의 경우 환율 변동에 따라 원화 환산 보호 금액이 달라질 수 있는 리스크가 존재합니다."
    }
]

generator = Generator()

# 2. 답변 생성 테스트
query = "FDIC의 예금자 보호 한도와 리스크는 무엇인가요?"
print(f"🔍 질문: {query}\n" + "="*50)

answer = generator.generate(query, mock_chunks)

# 3. 결과 출력
print(answer)