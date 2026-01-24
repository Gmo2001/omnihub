import os
import json
import time
import random
import string
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from pypdf import PdfReader, PdfWriter
from tqdm import tqdm

# =============================================================================
# 1. 사용자 설정 (★★★ 여기를 꼭 수정하세요 ★★★)
# =============================================================================
from pathlib import Path

# =============================================================================
# 1. 사용자 설정 (★★★ 여기를 꼭 수정하세요 ★★★)
# =============================================================================
# 구글 클라우드 프로젝트 ID (이름X, ID를 넣으세요. 예: omnihub-project-1234)
PROJECT_ID = "jnu-rise-edu-147" 

BASE_DIR = Path(__file__).resolve().parent.parent

# 작업할 PDF가 들어있는 폴더 경로 (상대 경로 변환)
TARGET_ROOT_DIR = BASE_DIR / "data" / "output" / "Omnihub 회계법인"

# 생성될 JSONL 파일명 및 경로
OUTPUT_FILENAME = "omnihub_ai_metadata.jsonl"
OUTPUT_FILE_PATH = BASE_DIR / "data" / "output" / OUTPUT_FILENAME

# GCS 버킷 이름 (나중에 파일 올릴 곳)
BUCKET_NAME = "omnihub-accounting-docs"

# =============================================================================
# 2. AI 모델 설정
# =============================================================================
LOCATION = "us-central1" # 또는 asia-northeast3 (서울)

print(f"[*] 설정된 프로젝트 ID: {PROJECT_ID}")
print(f"[*] 대상 폴더: {TARGET_ROOT_DIR}")
print("--------------------------------------------------")

try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    # 비용 효율적인 Flash 모델 사용
    model = GenerativeModel("gemini-2.0-flash")
except Exception as e:
    print(f"[오류] Vertex AI 초기화 실패. 프로젝트 ID가 정확한지, 로그인이 되었는지 확인하세요.\n에러내용: {e}")
    exit()

# AI에게 내릴 지시사항
SYSTEM_PROMPT = """
당신은 'Omnihub 회계법인'의 전문 문서 관리자입니다. 
제공된 파일 경로와 파일명을 보고, 해당 문서에 가장 적합한 메타데이터를 JSON 형식으로 생성하세요.

[규칙]
1. date: 파일명에 날짜가 있으면 사용하고, 없으면 2023~2024년 평일 업무시간 중 하나를 랜덤 생성(ISO 8601 포맷: YYYY-MM-DDTHH:MM:SSZ).
2. author: 부서명(폴더명)에 어울리는 한국인 이름과 직급 생성 (예: 김철수 회계사, 이민지 대리).
3. security: 문서 중요도에 따라 'high', 'medium', 'low' 중 택 1.
4. summary: 파일 제목을 보고 내용을 유추하여 1문장으로 명확하게 요약.
5. tags: 문서 분류를 위한 영어 태그 2~4개 (예: ["tax", "report", "2024"]).

[반환 형식]
JSON 포맷만 반환하세요.
"""

# =============================================================================
# 3. 기능 함수들
# =============================================================================
def generate_file_id():
    """고유 ID 생성"""
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"fil_{suffix}"

def convert_to_pdf_date(iso_str):
    """ISO 날짜를 PDF 메타데이터용 날짜로 변환"""
    try:
        # 간단한 파싱
        dt = iso_str.replace("Z", "").split(".")[0]
        dt_obj = time.strptime(dt, "%Y-%m-%dT%H:%M:%S")
        return time.strftime("D:%Y%m%d%H%M%S", dt_obj)
    except:
        return "D:20240101090000"

def get_ai_scenario(filepath):
    """Gemini에게 메타데이터 요청"""
    filename = os.path.basename(filepath)
    rel_path = os.path.relpath(filepath, TARGET_ROOT_DIR)
    
    user_msg = f"""
    파일 경로: {rel_path}
    파일 이름: {filename}
    위 파일의 메타데이터 JSON을 만들어줘.
    """
    
    try:
        response = model.generate_content(
            [SYSTEM_PROMPT, user_msg],
            generation_config=GenerationConfig(
                response_mime_type="application/json", 
                temperature=0.4
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"\n[AI 오류] {filename} 처리 중 실패: {e}")
        return None

# =============================================================================
# 4. 메인 실행
# =============================================================================
def main():
    if not TARGET_ROOT_DIR.exists():
        print(f"[경로 오류] 폴더를 찾을 수 없습니다: {TARGET_ROOT_DIR}")
        return

    # PDF 파일 수집
    pdf_list = []
    for root, dirs, files in os.walk(str(TARGET_ROOT_DIR)):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_list.append(os.path.join(root, file))

    if not pdf_list:
        print("[알림] 처리할 PDF 파일이 없습니다.")
        return

    print(f"[*] 총 {len(pdf_list)}개의 PDF 파일을 AI로 분석합니다.")
    
    # 결과 저장할 JSONL 파일 경로
    # output_path = os.path.join(os.path.dirname(TARGET_ROOT_DIR), OUTPUT_FILENAME)
    
    success_count = 0

    with open(str(OUTPUT_FILE_PATH), 'w', encoding='utf-8') as f_out:
        # tqdm으로 진행률 표시
        for file_path in tqdm(pdf_list, desc="AI 처리 중", unit="file"):
            
            # 1. AI 메타데이터 생성
            meta = get_ai_scenario(file_path)
            if not meta:
                continue

            # 2. PDF 파일 속성(내부 메타데이터) 수정
            try:
                reader = PdfReader(file_path)
                writer = PdfWriter()
                writer.append_pages_from_reader(reader)
                
                pdf_date = convert_to_pdf_date(meta.get('date'))
                
                new_pdf_meta = {
                    "/Title": os.path.basename(file_path).replace(".pdf", ""),
                    "/Author": meta.get('author', 'Omnihub AI'),
                    "/Subject": meta.get('summary', ''),
                    "/Keywords": ", ".join(meta.get('tags', [])),
                    "/Creator": "Omnihub Smart System",
                    "/CreationDate": pdf_date,
                    "/ModDate": pdf_date
                }
                writer.add_metadata(new_pdf_meta)
                
                # 임시 파일로 저장 후 덮어쓰기
                temp_path = file_path + ".tmp"
                with open(temp_path, "wb") as f_tmp:
                    writer.write(f_tmp)
                
                # 원본 삭제 및 이름 변경 (파일이 사용 중이면 에러날 수 있음)
                os.remove(file_path)
                os.rename(temp_path, file_path)
                
            except Exception as e:
                print(f"\n[PDF 쓰기 오류] {os.path.basename(file_path)}: {e}")
                if os.path.exists(file_path + ".tmp"):
                    os.remove(file_path + ".tmp")
                # PDF 수정 실패해도 JSONL은 기록하도록 진행

            # 3. GCP 검색용 JSONL 데이터 생성
            rel_path = os.path.relpath(file_path, TARGET_ROOT_DIR)
            gcs_uri = f"gs://{BUCKET_NAME}/Omnihub_Data/{rel_path.replace(os.sep, '/')}"
            
            # 폴더 구조를 가상 경로로
            virtual_path = "/" + os.path.dirname(rel_path).replace(os.sep, "/")
            if virtual_path == "/": virtual_path = "/Uncategorized"

            doc_record = {
                "fileId": generate_file_id(),
                "title": os.path.basename(file_path),
                "source": "upload",
                "mimeType": "application/pdf",
                "sizeBytes": os.path.getsize(file_path),
                "author": meta.get('author'),
                "virtualPath": virtual_path,
                "tags": meta.get('tags'),
                "securityLevel": meta.get('security'),
                "docStatus": "approved",
                "ssot": True if meta.get('security') == 'high' else False,
                "summary": meta.get('summary'),
                "createdAt": meta.get('date'),
                "updatedAt": meta.get('date')
            }

            # Vertex AI Search 포맷
            final_data = {
                "id": doc_record["fileId"],
                "structData": doc_record,
                "content": {
                    "mimeType": "application/pdf",
                    "uri": gcs_uri
                }
            }
            
            f_out.write(json.dumps(final_data, ensure_ascii=False) + "\n")
            success_count += 1
            
            # 너무 빠른 요청 방지
            time.sleep(0.5)

    print("\n" + "=" * 60)
    print(f"[완료] 총 {success_count}개의 파일 처리 완료")
    print(f"생성된 파일: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()