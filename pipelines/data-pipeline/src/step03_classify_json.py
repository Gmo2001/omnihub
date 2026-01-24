import os
import json
import csv
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

from pathlib import Path

# ==========================================
# [설정] 경로 수정
BASE_DIR = Path(__file__).resolve().parent.parent

# JSON 파일들이 들어있는 입력 폴더
target_folder_path = BASE_DIR / "data" / "input" / "json_raw"

# CSV 결과 파일이 저장될 경로 (출력)
output_dir = BASE_DIR / "data" / "output" / "accounting_list"
# 폴더가 없으면 생성 (Pool 사용 시 미리 생성 권장)
if not output_dir.exists():
    output_dir.mkdir(parents=True, exist_ok=True)

csv_save_path = output_dir / "회계문서_목록.csv"

# [설정] 회계 관련 키워드
ACCOUNTING_KEYWORDS = [
    "지출", "결의", "정산", "계약", "청구", 
    "세금", "계산서", "예산", "구매", "구입", 
    "지급", "수당", "입찰", "견적", "영수증",
    "거래명세서", "납부", "발주", "회계", "비용"
]
# ==========================================

def process_single_file(file_path):
    """
    JSON 파일을 읽어서 회계 관련 키워드가 있는지 확인하고,
    있으면 모든 데이터를 추출하여 반환합니다.
    """
    try:
        # 1. 파일 읽기
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 2. 키워드 검사를 위한 텍스트 수집
        text_content = ""
        
        # raw_data_info에서 텍스트 추출
        raw_info = data.get('raw_data_info', {})
        if raw_info:
            text_content += str(raw_info.get('doc_name', '')) + " "
            text_content += str(raw_info.get('doc_type', '')) + " "
        
        # learning_data_info에서 텍스트 추출
        learn_info = data.get('learning_data_info', {})
        if learn_info:
            text_content += str(learn_info.get('plain_text', '')) + " "
            text_content += str(learn_info.get('class_name', '')) + " "

        # 3. 회계 키워드 검사
        is_accounting = False
        matched_keyword = ""
        for keyword in ACCOUNTING_KEYWORDS:
            if keyword in text_content:
                is_accounting = True
                matched_keyword = keyword
                break
        
        # 4. 회계 관련 문서인 경우 모든 데이터 추출
        if is_accounting:
            # raw_data_info 필드 추출
            doc_name = raw_info.get('doc_name', '')
            date = raw_info.get('date', '')
            doc_type = raw_info.get('doc_type', '')
            format_type = raw_info.get('format', '')
            page_direction = raw_info.get('page_direction', '')
            copyright_info = raw_info.get('copyright', '')
            organ_type = raw_info.get('organ_type', '')
            publisher = raw_info.get('publisher', '')
            
            # source_data_info 필드 추출
            source_info = data.get('source_data_info', {})
            raw_data_name = source_info.get('raw_data_name', '')
            source_data_name_pdf = source_info.get('source_data_name_pdf', '')
            source_data_name_jpg = source_info.get('source_data_name_jpg', '')
            document_resolution = source_info.get('document_resolution', [])
            resolution_str = f"{document_resolution[0]}x{document_resolution[1]}" if len(document_resolution) == 2 else ""
            
            # learning_data_info 필드 추출
            learning_data_name = learn_info.get('learning_data_name', '')
            page_num = learn_info.get('page_num', '')
            class_num = learn_info.get('class_num', '')
            bounding_box = learn_info.get('bounding_box', [])
            bbox_str = ",".join(map(str, bounding_box)) if bounding_box else ""
            class_name = learn_info.get('class_name', '')
            plain_text = learn_info.get('plain_text', '')
            
            return {
                'status': 'accounting',
                'data': {
                    '파일경로': file_path,
                    '파일명': os.path.basename(file_path),
                    '매칭키워드': matched_keyword,
                    # raw_data_info
                    '문서명': doc_name,
                    '날짜': date,
                    '문서유형': doc_type,
                    '포맷': format_type,
                    '페이지방향': page_direction,
                    '저작권': copyright_info,
                    '기관유형': organ_type,
                    '발행처': publisher,
                    # source_data_info
                    '원본파일명': raw_data_name,
                    'PDF파일명': source_data_name_pdf,
                    'JPG파일명': source_data_name_jpg,
                    '문서해상도': resolution_str,
                    # learning_data_info
                    '학습데이터명': learning_data_name,
                    '페이지번호': page_num,
                    '클래스번호': class_num,
                    '바운딩박스': bbox_str,
                    '클래스명': class_name,
                    '텍스트내용': plain_text
                }
            }
        else:
            return {'status': 'not_accounting'}

    except Exception as e:
        return {'status': 'error', 'msg': str(e), 'path': file_path}

def main():
    print(f"📂 파일 목록 수집 중... (경로: {target_folder_path})")
    
    # 모든 JSON 파일 찾기
    target_files = []
    # Path 객체 호환성 위해 str 변환
    for root, dirs, files in os.walk(str(target_folder_path)):
        for filename in files:
            if filename.lower().endswith('.json'):
                target_files.append(os.path.join(root, filename))
    
    total_files = len(target_files)
    print(f"✅ 총 {total_files}개의 JSON 파일을 찾았습니다.")
    print("-" * 60)

    stats = {"accounting": 0, "not_accounting": 0, "error": 0}
    accounting_data_list = []  # CSV로 저장할 데이터 리스트

    if total_files > 0:
        print("🔍 회계 관련 문서 검색 중...")
        with Pool(processes=cpu_count()) as pool:
            for result in tqdm(pool.imap_unordered(process_single_file, target_files, chunksize=50), total=total_files):
                
                status = result.get('status')

                if status == 'accounting':
                    stats["accounting"] += 1
                    accounting_data_list.append(result['data'])
                
                elif status == 'not_accounting':
                    stats["not_accounting"] += 1
                
                elif status == 'error':
                    stats["error"] += 1
                    # 에러 정보 출력 (선택사항)
                    # print(f"\n⚠️ 에러: {result.get('path', 'Unknown')} - {result.get('msg', 'Unknown error')}")

    print("-" * 60)
    print("🎉 작업 완료!")
    print(f"📊 회계 관련 문서  : {stats['accounting']}개")
    print(f"� 일반 문서       : {stats['not_accounting']}개")
    print(f"⚠️ 에러 발생       : {stats['error']}개")

    # CSV 파일 저장
    if accounting_data_list:
        print(f"\n💾 CSV 파일 저장 중... ({csv_save_path})")
        try:
            # CSV 헤더 (첫 번째 데이터의 키를 사용)
            headers = list(accounting_data_list[0].keys())
            
            with open(csv_save_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(accounting_data_list)
            
            print(f"✅ CSV 저장 완료! ({len(accounting_data_list)}개 항목)")
            print(f"📁 저장 위치: {csv_save_path}")
        except Exception as e:
            print(f"❌ CSV 저장 실패: {e}")
    else:
        print("\n📭 회계 관련 문서가 없어서 CSV를 생성하지 않았습니다.")

if __name__ == "__main__":
    main()