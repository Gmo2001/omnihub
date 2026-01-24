import pandas as pd
from bs4 import BeautifulSoup
import requests
import time
import os
import re
from datetime import datetime
from tqdm import tqdm

# ==============================================================================
from pathlib import Path
import glob

# ==============================================================================
# 1. 설정 및 경로 지정
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# Step 1 결과물이 저장된 폴더 (입력)
LINKS_DIR = BASE_DIR / "data" / "output" / "links"

# Step 2 결과 저장 폴더 (출력)
OUTPUT_DIR = BASE_DIR / "data" / "output" / "items"

# 폴더가 없으면 생성
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SAVE_INTERVAL_SECONDS = 2 * 60 * 60  # 2시간 (초 단위)

# 크롤링 차단 방지용 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ==============================================================================
# 2. 파싱 로직
# ==============================================================================
def parse_html_content(url, html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    data = {'URL': url}

    try:
        # [기본] 제목
        title_tag = soup.select_one('div.dataHead h3')
        if title_tag:
            data['제목'] = title_tag.get_text(strip=True).replace('NEW', '').strip()
        
        # [기본] 분야, 구분, 유형, 생성방식 (헤더 영역)
        info_list = soup.select('div.dataHead div.content ul li')
        
        data['구분'] = "" 
        
        for li in info_list:
            text = li.get_text(strip=True)
            if '분야' in text: 
                data['분야'] = text.replace('분야', '').strip()
            elif '구분' in text: 
                data['구분'] = text.replace('구분', '').strip()
            elif '유형' in text: 
                data['유형'] = text.replace('유형', '').strip()
            elif '생성 방식' in text: 
                data['생성 방식'] = text.replace('생성 방식', '').strip()

        # [보완] 상단 경고 문구에서 구분 추출 (안심구역 등)
        if not data['구분']:
            safety_head = soup.select_one('div.dataHead div.safetyHead')
            if safety_head:
                raw_text = safety_head.get_text(strip=True)
                clean_text = raw_text.replace('본 데이터는', '').replace('입니다.', '').strip()
                data['구분'] = clean_text

        # [추가] 해시태그
        tags = soup.select('div.dataHead span.tag a')
        if tags:
            tag_list = [tag.get_text(strip=True) for tag in tags]
            data['태그'] = ", ".join(tag_list)
        else:
            data['태그'] = ""

        # [기본] 구축년도, 조회수, 다운로드
        date_span = soup.select_one('div.dataHead span.date')
        if date_span:
            for em in date_span.find_all('em'):
                text = em.get_text(strip=True)
                if '구축년도' in text: data['구축년도'] = text.split(':')[-1].strip()
                if '갱신년월' in text: data['갱신년월'] = text.split(':')[-1].strip()
                if '조회수' in text: data['관심수'] = text.split(':')[-1].strip().replace(',', '')
                if '다운로드' in text: data['다운로드'] = text.split(':')[-1].strip().replace(',', '')

        # [기본] 파일 용량
        size_match = re.search(r"var s3FileSize = '(\d+)';", html_text)
        if size_match:
            bytes_size = int(size_match.group(1))
            data['용량(MB)'] = round(bytes_size / (1024 * 1024), 2)
        else:
            data['용량(MB)'] = 0

        # [중요] 메타데이터 구조표 파싱 (데이터 형식, 출처, 라벨링, 활용서비스)
        meta_table = None
        # caption에 "메타데이터 구조표"가 포함된 테이블 찾기
        for table in soup.select('table.data.metadata'):
            if "메타데이터 구조표" in table.get_text():
                meta_table = table
                break
        
        # 메타데이터 표가 있으면 항목 검색
        if meta_table:
            # 모든 th(헤더)를 순회하며 옆의 td(값)를 찾음
            for th in meta_table.find_all('th'):
                header_text = th.get_text(strip=True)
                td = th.find_next_sibling('td') # th 바로 다음 형제인 td 찾기
                
                if td:
                    value = td.get_text(strip=True)
                    
                    if "데이터 형식" in header_text:
                        data['데이터형식'] = value
                    elif "데이터 출처" in header_text:
                        data['데이터출처'] = value
                    elif "라벨링 유형" in header_text:
                        data['라벨링유형'] = value
                    elif "데이터 활용 서비스" in header_text:
                        data['활용서비스'] = value

        # [추가] 통계 요약
        stats_div = soup.select_one('ul.fold.dataContent li:nth-of-type(3) div')
        if stats_div:
            first_stats_table = stats_div.select_one('table')
            if first_stats_table:
                table_text = []
                for tr in first_stats_table.select('tr'):
                    row_text = " | ".join([td.get_text(strip=True) for td in tr.find_all(['th', 'td'])])
                    table_text.append(row_text)
                data['통계요약'] = " // ".join(table_text[:5])
        
        # [기본] 소개 텍스트
        intro_text = []
        for pre in soup.select('pre.srchKwrdHighlight'):
            intro_text.append(pre.get_text(strip=True))
        data['소개'] = " ".join(intro_text)[:500]

    except Exception as e:
        data['에러'] = str(e)
    
    return data

# ==============================================================================
# 3. 데이터 저장 함수
# ==============================================================================
def save_data(data_list, output_folder):
    if not data_list:
        return
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"aihub_items_result_{timestamp}.csv"
    filepath = os.path.join(output_folder, filename)

    df = pd.DataFrame(data_list)
    
    # [수정됨] 컬럼 순서 지정: 새로 추가된 3개 항목 반영, '구분'은 맨 뒤
    cols = [
        'URL', '제목', '분야', '태그', '유형', 
        '데이터형식', '데이터출처', '라벨링유형', '활용서비스', # <-- 추가된 항목
        '용량(MB)', '구축년도', '관심수', '다운로드', 
        '소개', '통계요약', '에러', '구분'
    ]
    
    # 존재하는 컬럼만 선택하여 정렬
    existing_cols = [c for c in cols if c in df.columns]
    remain_cols = [c for c in df.columns if c not in cols]
    
    df = df[existing_cols + remain_cols]

    # utf-8-sig로 저장 (한글 깨짐 방지)
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"\n[저장 완료] {len(data_list)}건이 '{filename}'에 저장되었습니다.")

# ==============================================================================
# 4. 메인 실행 로직
# ==============================================================================
def main():
    try:
        print(f"[*] 입력 데이터 폴더 확인 중: {LINKS_DIR}")
        
        # LINKS_DIR 내의 모든 csv 파일 검색
        csv_files = list(LINKS_DIR.glob("*.csv"))
        
        if not csv_files:
            print(f"[오류] '{LINKS_DIR}' 폴더에 CSV 파일이 없습니다. Step 1을 먼저 실행하세요.")
            return

        # 가장 최근에 수정된 파일 선택
        latest_file = max(csv_files, key=os.path.getmtime)
        print(f"[*] 최신 입력 파일 선택됨: {latest_file.name}")

        df_urls = pd.read_csv(latest_file)
        
        # 'URL' 컬럼 확인
        if 'URL' not in df_urls.columns:
            print(f"[오류] 입력 파일에 'URL' 컬럼이 없습니다. (컬럼: {list(df_urls.columns)})")
            # 혹시 컬럼명이 다를 경우를 대비해 첫번째 컬럼을 시도할 수도 있음 (선택사항)
            # url_list = df_urls.iloc[:, -1].tolist() # 보통 URL은 마지막에 위치
            return

        url_list = df_urls['URL'].dropna().tolist()
        print(f"[*] 총 {len(url_list)}개의 링크를 찾았습니다.")

    except Exception as e:
        print(f"[오류] 입력 파일을 읽는 중 문제가 발생했습니다: {e}")
        return

    collected_data = []
    last_save_time = time.time()

    print("크롤링 시작... (중단하려면 Ctrl+C를 누르세요)")

    try:
        for url in tqdm(url_list, desc="진행 중", unit="page"):
            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                
                if response.status_code == 200:
                    item_data = parse_html_content(url, response.text)
                    collected_data.append(item_data)
                else:
                    collected_data.append({'URL': url, '에러': f'Status {response.status_code}'})

            except Exception as e:
                collected_data.append({'URL': url, '에러': f'Request Fail: {str(e)}'})

            # 2시간 주기 저장
            current_time = time.time()
            if current_time - last_save_time >= SAVE_INTERVAL_SECONDS:
                print(f"\n[알림] 2시간이 경과하여 중간 저장을 수행합니다. (현재 {len(collected_data)}건)")
                save_data(collected_data, OUTPUT_DIR)
                collected_data = []
                last_save_time = current_time

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n[강제 종료] 사용자에 의해 작업을 중단합니다.")
        print("현재까지 수집된 데이터를 저장합니다...")
    
    except Exception as e:
        print(f"\n[오류 발생] 예상치 못한 오류: {e}")
        
    finally:
        if collected_data:
            save_data(collected_data, OUTPUT_DIR)
        else:
            print("\n저장할 새로운 데이터가 없습니다.")

        print("프로그램을 종료합니다.")

if __name__ == "__main__":
    main()