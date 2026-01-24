import os
import csv
from tqdm import tqdm

# =============================================================================
# 1. 설정
# =============================================================================
from pathlib import Path

# =============================================================================
# 1. 설정
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# 이름 매핑 CSV 경로 (./data/mapping/filename_map.csv)
NAME_CSV_PATH = BASE_DIR / "data" / "mapping" / "filename_map.csv"

# 검색 및 이름 변경을 수행할 최상위 루트 폴더 (./data/output/Omnihub 회계법인)
TARGET_ROOT_DIR = BASE_DIR / "data" / "output" / "Omnihub 회계법인"

def rename_files_in_structure():
    # 1. CSV 파일 읽어서 매핑 딕셔너리 생성
    # key: 원본파일이름 (예: OC2_240729_TY2-1_0001.pdf)
    # value: 바꿀이름 (예: 충북도, 특성화시장 등 24곳 중기부 공모사업 선정.pdf)
    
    if not NAME_CSV_PATH.exists():
        print(f"[오류] CSV 파일을 찾을 수 없습니다: {NAME_CSV_PATH}")
        return

    name_map = {}
    
    print("[*] 이름 매핑 정보를 읽어옵니다...")
    try:
        # 탭(\t)으로 구분된 파일 읽기
        with open(str(NAME_CSV_PATH), 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                if len(row) >= 2:
                    original_name = row[0].strip()
                    new_name_base = row[1].strip()
                    
                    # 확장자 처리 (.pdf가 새 이름에 없으면 붙여줌)
                    if not new_name_base.lower().endswith('.pdf'):
                        new_name = f"{new_name_base}.pdf"
                    else:
                        new_name = new_name_base
                        
                    name_map[original_name] = new_name
    except UnicodeDecodeError:
         # utf-8 실패 시 cp949 재시도
        with open(str(NAME_CSV_PATH), 'r', encoding='cp949') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                if len(row) >= 2:
                    original_name = row[0].strip()
                    new_name_base = row[1].strip()
                    if not new_name_base.lower().endswith('.pdf'):
                        new_name = f"{new_name_base}.pdf"
                    else:
                        new_name = new_name_base
                    name_map[original_name] = new_name

    print(f"[*] 총 {len(name_map)}개의 변경 대상 파일명을 로드했습니다.")
    print("-" * 60)

    # 2. 폴더 순회하며 파일 이름 변경
    success_cnt = 0
    fail_cnt = 0
    skip_cnt = 0 # 매핑 정보가 없어서 건너뛴 파일

    # os.walk로 모든 하위 폴더 탐색
    # tqdm 연동을 위해 파일 리스트를 미리 수집하는 것이 좋지만, 
    # 여기서는 간단히 폴더 단위로 진행상황을 보여주거나, 실시간 로그를 출력합니다.
    
    all_files = []
    for root, dirs, files in os.walk(TARGET_ROOT_DIR):
        for file in files:
            all_files.append(os.path.join(root, file))

    print(f"[*] 폴더 스캔 완료. 총 {len(all_files)}개의 파일을 검사합니다.")
    
    for file_path in tqdm(all_files, desc="이름 변경 중", unit="file"):
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)

        # 매핑 정보에 해당 파일이 있는지 확인
        if filename in name_map:
            new_filename = name_map[filename]
            
            # 윈도우 파일명 금지 문자 제거 (\ / : * ? " < > |)
            # 안전한 이름으로 변경
            safe_new_name = "".join(c for c in new_filename if c not in r'<>:"/\|?*')
            
            new_file_path = os.path.join(dirname, safe_new_name)

            try:
                # 이름 변경 실행
                os.rename(file_path, new_file_path)
                success_cnt += 1
            except Exception as e:
                # tqdm.write(f"[에러] {filename} -> {safe_new_name} 변경 실패: {e}")
                fail_cnt += 1
        else:
            skip_cnt += 1

    print("-" * 60)
    print(f"[작업 완료]")
    print(f" - 이름 변경 성공: {success_cnt}건")
    print(f" - 이름 변경 실패: {fail_cnt}건")
    print(f" - 매핑 정보 없음(건너뜀): {skip_cnt}건")
    print("-" * 60)

if __name__ == "__main__":
    rename_files_in_structure()