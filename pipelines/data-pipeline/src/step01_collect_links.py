import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import re
import math
from datetime import datetime
from tqdm import tqdm

from pathlib import Path

# =============================================================================
# 1. 설정 및 초기화
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# 저장할 폴더 경로 (./data/output/links)
SAVE_DIR = BASE_DIR / "data" / "output" / "links"

# 폴더가 없으면 생성
if not SAVE_DIR.exists():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

# 파일명 설정 (타임스탬프 포함)
current_time_str = datetime.now().strftime("%Y%m%d_%H%M")
file_name = f"aihub_result_{current_time_str}.csv"
full_path = SAVE_DIR / file_name

# 2시간(초 단위) 설정
SAVE_INTERVAL = 2 * 60 * 60 

# URL 및 헤더 설정
BASE_URL = "https://aihub.or.kr/aihubdata/data/list.do"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ==========================================
# 2. 기능 함수 정의
# ==========================================

def save_to_csv(data_list, filepath):
    """
    데이터를 CSV에 이어쓰기(append)하고 메모리상의 리스트를 비웁니다.
    """
    if not data_list:
        return

    # 컬럼 순서 지정 (보기 좋게 정렬)
    columns = ['ID', '카테고리', '제목', '구축년도', '용량(MB)', '조회수', '관심수', '다운로드수', 'URL']
    df = pd.DataFrame(data_list, columns=columns)
    
    # 파일이 없으면 헤더 포함 저장, 있으면 헤더 빼고 내용만 이어붙이기
    if not os.path.exists(filepath):
        df.to_csv(filepath, index=False, encoding='utf-8-sig', mode='w')
    else:
        df.to_csv(filepath, index=False, encoding='utf-8-sig', mode='a', header=False)
    
    print(f"\n[Save] {len(data_list)}건 저장 완료 -> {filepath}")

# ==========================================
# 3. 크롤링 메인 로직
# ==========================================

def main():
    # 총 페이지 수 계산 (908건 기준 60개씩 = 16페이지)
    TOTAL_ITEMS = 908
    ITEMS_PER_PAGE = 60
    TOTAL_PAGES = math.ceil(TOTAL_ITEMS / ITEMS_PER_PAGE)

    temp_data = [] # 임시 저장소
    start_time = time.time()
    last_save_time = start_time

    print(f"크롤링 시작... 총 {TOTAL_PAGES}페이지 예정")
    print(f"저장 경로: {full_path}")
    print("-" * 50)

    try:
        # tqdm으로 진행바 표시
        for page in tqdm(range(1, TOTAL_PAGES + 1), desc="페이지 수집 중"):
            
            params = {
                'currMenu': '115', 'topMenu': '100',
                'srchOptnCnd': 'OPTNCND001', 'srchDetailCnd': 'DETAILCND001',
                'srchOrder': 'ORDER001', 'srchPagePer': '60',
                'pageIndex': page
            }

            response = requests.get(BASE_URL, headers=HEADERS, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('ul.dataList > li')

            if not items:
                break

            for item in items:
                try:
                    # 제목
                    title = item.select_one('.textBox .text').get_text(strip=True) if item.select_one('.textBox .text') else ""
                    # 카테고리
                    category = item.select_one('.kind').get_text(strip=True) if item.select_one('.kind') else ""
                    
                    # 통계 (조회/관심/다운)
                    # HTML 구조: <p><span class="view"><em>조회수</em></span>9,534</p>
                    # next_sibling을 이용해 span 태그 뒤에 있는 숫자 텍스트만 추출
                    views = item.select_one('.info .view').next_sibling.strip().replace(',', '') if item.select_one('.info .view') else "0"
                    likes = item.select_one('.info .like').next_sibling.strip().replace(',', '') if item.select_one('.info .like') else "0"
                    downloads = item.select_one('.info .down').next_sibling.strip().replace(',', '') if item.select_one('.info .down') else "0"
                    
                    # 용량 및 구축년도
                    vol_tag = item.select_one('.fileVolume')
                    vol_bytes = vol_tag.get_text(strip=True) if vol_tag else "0"
                    
                    # 구축년도 (속성값 추출)
                    cnstc_year = vol_tag.get('data-datacnstcyear') if vol_tag else ""
                    
                    # 용량 변환 (MB)
                    try:
                        vol_mb = round(int(vol_bytes) / (1024 * 1024), 2)
                    except:
                        vol_mb = 0
                    
                    # URL 및 ID
                    link_tag = item.find('a')
                    full_url = ""
                    dataset_id = ""
                    if link_tag and 'href' in link_tag.attrs:
                        href = link_tag['href']
                        full_url = f"https://aihub.or.kr{href}"
                        match = re.search(r'dataSetSn=(\d+)', href)
                        dataset_id = match.group(1) if match else ""

                    # 데이터 추가 (Dictionary)
                    temp_data.append({
                        'ID': dataset_id,
                        '카테고리': category,
                        '제목': title,
                        '구축년도': cnstc_year,   # 추가됨
                        '용량(MB)': vol_mb,
                        '조회수': views,
                        '관심수': likes,        # 추가됨
                        '다운로드수': downloads,
                        'URL': full_url
                        # '수집시간': ... (제거됨)
                    })

                except Exception as e:
                    continue

            # 2시간 주기 저장 체크
            if time.time() - last_save_time >= SAVE_INTERVAL:
                save_to_csv(temp_data, full_path)
                temp_data.clear()
                last_save_time = time.time()
            
            time.sleep(0.5)

        # 정상 종료 후 잔여 데이터 저장
        if temp_data:
            save_to_csv(temp_data, full_path)
            print("모든 수집이 완료되었습니다.")

    except KeyboardInterrupt:
        print("\n\n!!! 강제 종료 감지 !!!")
        print("현재까지 수집된 데이터를 저장하고 종료합니다...")
        if temp_data:
            save_to_csv(temp_data, full_path)
        print("안전하게 종료되었습니다.")

    except Exception as e:
        print(f"\n[Error] 오류 발생: {e}")
        if temp_data:
            save_to_csv(temp_data, full_path)

if __name__ == "__main__":
    main()