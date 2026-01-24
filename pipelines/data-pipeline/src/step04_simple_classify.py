import csv
import os
import time
from datetime import datetime
from tqdm import tqdm

# =============================================================================
# 1. 환경 설정
# =============================================================================

from pathlib import Path

# =============================================================================
# 1. 환경 설정
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# 입력: data/mapping/file_move_list.csv
INPUT_PATH = BASE_DIR / "data" / "mapping" / "file_move_list.csv"

# 출력: data/output/
OUTPUT_DIR = BASE_DIR / "data" / "output"
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 2. 분류 규칙 (Omnihub 회계법인 표준 DB 구조 반영)
# =============================================================================
# 우선순위: 서식/계약서 > 특수 컨설팅 > 세무/회계 실무 > 일반 리서치

CLASSIFICATION_RULES = [
    # -------------------------------------------------------------------------
    # 📁 00_전사_공유 (공용)
    # -------------------------------------------------------------------------
    {
        "folder": "00_전사_공유/02_표준서식_모음",
        "keywords": ["(비즈폼)", "서식", "양식", "PPT", "ppt", "템플릿", "사업계획서", "제안서"]
        # 비즈폼 등은 실무 파일이라기보다 '양식'으로 분류
    },
    {
        "folder": "00_전사_공유/05_시장_경제_동향", # (구조 유연성을 위해 항목 추가)
        "keywords": ["경제", "GDP", "연준", "FOMC", "금리", "환율", "물가", "인플레이션", "시장", "동향", "전망", "이슈"]
        # 제공해주신 리스트에 경제/뉴스 데이터가 많아 전사 공유 정보로 분류
    },

    # -------------------------------------------------------------------------
    # 📁 10_경영지원실 (내부 운영)
    # -------------------------------------------------------------------------
    {
        "folder": "10_경영지원실/13_계약_관리",
        "keywords": ["계약서", "약정서", "협약", "합의", "각서", "체결"]
    },
    {
        "folder": "10_경영지원실/11_인사_총무",
        "keywords": ["인사", "채용", "연봉", "급여", "복지", "휴가", "근로", "직원", "교육", "훈련"]
    },

    # -------------------------------------------------------------------------
    # 📁 50_재산제세_및_컨설팅 (특수 업무 / 고부가가치)
    # -------------------------------------------------------------------------
    {
        "folder": "50_재산제세_및_컨설팅/51_양도_상속_증여",
        "keywords": ["양도", "상속", "증여", "부동산", "토지", "주택"]
    },
    {
        "folder": "50_재산제세_및_컨설팅/54_주식평가_및_M&A",
        "keywords": ["가치평가", "Valuation", "M&A", "인수", "합병", "투자", "구조조정", "실사"]
    },
    {
        # 리스트에 많은 '관세/무역' 파일은 회계법인의 특수 컨설팅 영역으로 분류
        "folder": "50_재산제세_및_컨설팅/55_관세_무역_자문",
        "keywords": ["관세", "수출", "수입", "통관", "FTA", "물류", "해운", "선박", "항공", "운송", "무역", "원산지", "AEO", "보세"]
    },

    # -------------------------------------------------------------------------
    # 📁 20_법인세무_본부 (핵심 1 - 법인사업자)
    # -------------------------------------------------------------------------
    {
        "folder": "20_법인세무_본부/주요_거래처_모음",
        "keywords": ["삼성", "LG", "SK", "현대", "네이버", "카카오", "은행", "증권", "금융", "공사", "관세청"]
        # 특정 기업명이 있는 파일은 법인세무 폴더로 이동
    },
    {
        "folder": "20_법인세무_본부/02_부가가치세_및_결산",
        "keywords": ["법인세", "부가세", "부가가치세", "결산", "재무제표", "세무조정"]
    },

    # -------------------------------------------------------------------------
    # 📁 30_개인세무_본부 (핵심 2 - 개인사업자)
    # -------------------------------------------------------------------------
    {
        "folder": "30_개인세무_본부/03_종합소득세_신고",
        "keywords": ["소득세", "종합소득세", "연말정산", "원천세", "지급명세서", "자영업"]
    },

    # -------------------------------------------------------------------------
    # 📁 40_회계감사_본부 (Audit)
    # -------------------------------------------------------------------------
    {
        "folder": "40_회계감사_본부/42_진행_프로젝트",
        "keywords": ["감사", "Audit", "내부회계", "K-GAAP", "IFRS", "검토"]
    },
    
    # -------------------------------------------------------------------------
    # 📁 10_지식_리서치 (공공정책 등 잔여 데이터)
    # -------------------------------------------------------------------------
    {
        "folder": "00_전사_공유/06_공공정책_및_법규",
        "keywords": ["정책", "법안", "개정", "규제", "제도", "입법", "지원", "대책"]
    }
]

def classify_filename(filename):
    """파일명의 키워드를 분석하여 Omnihub 폴더 경로를 반환"""
    target_name = filename.strip()
    
    # 규칙 순회 (상위 규칙부터 우선 적용)
    for rule in CLASSIFICATION_RULES:
        if any(keyword.lower() in target_name.lower() for keyword in rule["keywords"]):
            return rule["folder"]
    
    # 어디에도 속하지 않으면 임시 폴더로
    return "99_미분류_및_임시"

def main():
    # 1. 파일 존재 여부 확인
    if not INPUT_PATH.exists():
        print(f"[오류] 입력 파일을 찾을 수 없습니다: {INPUT_PATH}")
        return

    # 2. 출력 파일명 생성 (타임스탬프 포함)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"simple_classify_result_{timestamp}.csv"
    output_path = OUTPUT_DIR / output_filename

    print(f"[*] Omnihub 회계법인 DB 분류 작업을 시작합니다.")
    print(f"[*] 입력 파일: {INPUT_PATH}")
    
    try:
        lines = []
        # 파일 읽기 (인코딩 자동 감지 시도 + CSV 파싱)
        try:
            with open(INPUT_PATH, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f, delimiter='\t')
                lines = list(reader)
        except UnicodeDecodeError:
            with open(INPUT_PATH, 'r', encoding='cp949', newline='') as f:
                reader = csv.reader(f, delimiter='\t')
                lines = list(reader)

        results = []
        
        # 3. tqdm을 사용한 진행 상황 표시 및 분류 실행
        print("[*] 문서 분류 중...")
        for idx, row in tqdm(enumerate(lines), total=len(lines), desc="진행률", unit="건"):
            if not row: continue # 빈 줄 건너뜀
            
            # 첫 번째 컬럼이 파일명이라고 가정
            filename = row[0].strip()
            if not filename: continue
            
            # CSV 형태의 따옴표 제거 등 전처리
            clean_filename = filename.strip('"')
            
            # 분류 로직 수행
            target_folder = classify_filename(clean_filename)
            
            # 결과 저장 (순번, 분류폴더, 원본파일명)
            results.append([idx + 1, target_folder, clean_filename])

        # 4. 결과 CSV 저장 (utf-8-sig 사용: 엑셀 한글 깨짐 방지)
        print(f"[*] 결과 파일 저장 중: {output_filename}")
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            # 헤더 작성 (한글)
            writer.writerow(["순번", "분류_폴더_경로", "파일_제목"])
            # 데이터 작성
            writer.writerows(results)

        print("-" * 60)
        print(f"[완료] 작업이 성공적으로 끝났습니다.")
        print(f" - 총 분류된 문서: {len(results)}건")
        print(f" - 저장 위치: {output_path}")
        print("-" * 60)

    except Exception as e:
        print(f"[오류] 처리 중 문제가 발생했습니다: {e}")

if __name__ == "__main__":
    main()