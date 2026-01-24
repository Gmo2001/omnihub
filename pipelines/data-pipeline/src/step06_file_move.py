import os
import csv
import shutil
from tqdm import tqdm

# =============================================================================
# 1. 설정
# =============================================================================
from pathlib import Path

# =============================================================================
# 1. 설정
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_FILE_PATH = BASE_DIR / "data" / "mapping" / "file_move_list.csv"

def move_files_from_csv():
    # 파일 존재 확인
    if not CSV_FILE_PATH.exists():
        print(f"[오류] CSV 파일을 찾을 수 없습니다: {CSV_FILE_PATH}")
        return

    print(f"[*] 데이터 읽기 시작: {CSV_FILE_PATH}")
    
    rows = []
    
    # 인코딩 자동 감지 및 파일 읽기 (utf-8 시도 후 실패 시 cp949)
    try:
        f = open(CSV_FILE_PATH, 'r', encoding='utf-8', newline='')
        # 탭(\t)으로 구분된 파일로 가정 (제공해주신 데이터 형태 기준)
        reader = csv.reader(f, delimiter='\t')
        rows = list(reader)
    except UnicodeDecodeError:
        f.close()
        # Path 객체는 open()에 바로 쓸 수 있지만, 인코딩 문제시 문자열로 변환 안전하게
        f = open(str(CSV_FILE_PATH), 'r', encoding='cp949', newline='')
        reader = csv.reader(f, delimiter='\t')
        rows = list(reader)
    except Exception as e:
        print(f"[오류] 파일을 읽는 중 문제가 발생했습니다: {e}")
        return

    # 헤더 제거 (첫 줄이 '파일 이름', '이 파일 있는 경로'... 인 경우)
    if rows and "파일 이름" in rows[0][0]:
        rows = rows[1:]

    print(f"[*] 총 {len(rows)}개의 파일 이동 작업을 시작합니다.")
    print("-" * 60)

    success_cnt = 0
    fail_cnt = 0

    # tqdm으로 진행률 표시
    for row in tqdm(rows, desc="파일 이동 중", unit="file"):
        if len(row) < 3:
            continue  # 데이터가 부족한 줄은 건너뜀

        file_name = row[0].strip()       # 파일 이름
        raw_src_dir = row[1].strip()     # 현재 경로 (CSV 원본)
        raw_dst_dir = row[2].strip()     # 이동할 경로 (CSV 원본)

        # [수정] 폴더명 변경(예: 03_aihub -> Other)에도 대응할 수 있도록 로직 개선
        # CSV에 기록된 경로 중 'data' 폴더가 포함되어 있다면, 이를 기준으로 상대 경로를 계산하여
        # 현재 프로젝트의 data 폴더로 매핑합니다.
        
        def resolve_path(raw_path):
            norm_path = raw_path.replace("\\", "/")
            
            # 1. 'data' anchoring (Best)
            if "/data/" in norm_path:
                rel_suffix = norm_path.split("/data/", 1)[1]
                return BASE_DIR / "data" / rel_suffix

            # 2. current folder name anchoring (For future compatibility)
            # 현재 폴더명(예: NewProject)이 경로에 포함되어 있다면 그 뒤를 떼옴
            current_root = BASE_DIR.name
            if f"/{current_root}/" in norm_path:
                 rel_suffix = norm_path.split(f"/{current_root}/", 1)[1]
                 return BASE_DIR / rel_suffix
            
            # 3. legacy '03_aihub' anchoring (Fallback)
            if "03_aihub" in norm_path:
                 rel_suffix = norm_path.split("03_aihub")[-1].lstrip("/")
                 return BASE_DIR / rel_suffix
            
            return Path(raw_path)

        # 1. 소스 경로 보정
        src_dir_path = resolve_path(raw_src_dir)

        # 2. 목적지 경로 보정
        dst_dir_path = resolve_path(raw_dst_dir)

        # 전체 경로 결합
        src_path = src_dir_path / file_name
        dst_path = dst_dir_path / file_name

        try:
            # 1. 원본 파일 확인
            if not os.path.exists(src_path):
                # tqdm 진행바 깨짐 방지를 위해 tqdm.write 사용
                # tqdm.write(f"[실패] 원본 없음: {file_name}") 
                fail_cnt += 1
                continue

            # 2. 목적지 폴더 생성 (없으면 자동 생성)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            # 3. 파일 이동 (shutil.move)
            shutil.move(src_path, dst_path)
            success_cnt += 1

        except Exception as e:
            tqdm.write(f"[에러] {file_name} 이동 실패: {e}")
            fail_cnt += 1
    
    # 파일 닫기
    f.close()

    print("-" * 60)
    print(f"[작업 완료]")
    print(f" - 성공: {success_cnt}건")
    print(f" - 실패: {fail_cnt}건 (원본이 없거나 권한 문제 등)")
    print("-" * 60)

if __name__ == "__main__":
    move_files_from_csv()