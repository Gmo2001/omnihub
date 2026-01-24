import os
import time
from tqdm import tqdm

# =============================================================================
# 1. 설정: 경로 및 폴더 구조 정의
# =============================================================================

# 1. 최상위 경로 (요청하신 경로)
from pathlib import Path

# 1. 최상위 경로 (상대 경로로 변경: project_root/data/output)
# src/step05_folder_gen.py 위치 기준 -> 부모(src) -> 부모(root) -> data -> output
BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_BASE_PATH = os.path.join(BASE_DIR, "data", "output")

# 2. 회계법인 이름 (루트 폴더)
ROOT_NAME = "Omnihub 회계법인"

# 3. 생성할 하위 폴더 리스트 (제공해주신 경로 반영)
SUB_FOLDERS = [
    "00_전사_공유/02_표준서식_모음",
    "00_전사_공유/05_시장_경제_동향",
    "00_전사_공유/06_공공정책_및_법규",
    
    "10_경영지원실/11_인사_총무",
    "10_경영지원실/13_계약_관리",
    
    "20_법인세무_본부/주요_거래처_모음",
    "20_법인세무_본부/02_부가가치세_및_결산",
    
    "30_개인세무_본부/03_종합소득세_신고",
    
    "40_회계감사_본부/42_진행_프로젝트",
    
    "50_재산제세_및_컨설팅/51_양도_상속_증여",
    "50_재산제세_및_컨설팅/54_주식평가_및_M&A",
    "50_재산제세_및_컨설팅/55_관세_무역_자문",
    
    "99_미분류_및_임시"  # 분류되지 않은 파일용 폴더 (필요시 사용)
]

def create_folder_structure():
    # 최종 루트 경로 생성 ( .../폴더를 저장할 폴더/Omnihub 회계법인 )
    full_root_path = os.path.join(TARGET_BASE_PATH, ROOT_NAME)

    print(f"[*] Omnihub 회계법인 폴더 생성을 시작합니다.")
    print(f"[*] 설치 경로: {full_root_path}")
    print("-" * 60)

    try:
        # 폴더 리스트 정렬 (보기 좋게 순서대로 생성)
        sorted_folders = sorted(SUB_FOLDERS)

        # tqdm을 이용한 진행바 표시
        for sub_folder in tqdm(sorted_folders, desc="폴더 생성 중", unit="폴더"):
            # 경로 생성 (운영체제에 맞게 / 를 \ 로 변환)
            folder_path = os.path.join(full_root_path, sub_folder.replace("/", os.sep))
            
            # 실제 폴더 생성 (exist_ok=True: 이미 있어도 에러 없이 진행)
            os.makedirs(folder_path, exist_ok=True)
            
            # 진행 과정을 눈으로 확인하기 위해 아주 짧은 딜레이 추가
            time.sleep(0.1)

        print("-" * 60)
        print("[완료] 폴더 구조 생성이 끝났습니다.")
        print(f"[확인] 폴더 위치: {full_root_path}")

    except Exception as e:
        print(f"\n[오류] 폴더 생성 중 문제가 발생했습니다: {e}")

if __name__ == "__main__":
    create_folder_structure()