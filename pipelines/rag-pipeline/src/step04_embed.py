import os
import json
import time
from tqdm import tqdm
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

# =============================================================================
# [설정 정보]
# =============================================================================
PROJECT_ID = "jnu-rise-edu-147"
LOCATION = "us-central1"
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

# 1. 입력: 청킹 완료된 데이터
# 스크립트 위치 기준(src)으로 상위 폴더(project root)를 찾아 경로 설정
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR) # src 상위가 프로젝트 루트

INPUT_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "chunks.jsonl")

# 2. 출력: 임베딩 결과 (벡터 데이터)
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "embeddings.jsonl")

# 3. 모델 설정
MODEL_NAME = "text-embedding-004" # 다국어 성능 우수
BATCH_SIZE = 5 # 한 번에 처리할 청크 개수 (Quota 고려)

# =============================================================================
# [초기화]
# =============================================================================
print(f"[*] Vertex AI 초기화 중... (Model: {MODEL_NAME})")
vertexai.init(project=PROJECT_ID, location=LOCATION)
model = TextEmbeddingModel.from_pretrained(MODEL_NAME)

# =============================================================================
# [함수 정의]
# =============================================================================
def get_embeddings_batch(texts):
    """
    텍스트 리스트를 받아 벡터 리스트를 반환
    task_type="RETRIEVAL_DOCUMENT" : DB 저장용 임베딩
    """
    # 빈 텍스트 제거 및 입력 객체 생성
    inputs = [TextEmbeddingInput(text, "RETRIEVAL_DOCUMENT") for text in texts]
    
    try:
        embeddings = model.get_embeddings(inputs)
        # 결과에서 벡터 값(values)만 추출
        return [embedding.values for embedding in embeddings]
    except Exception as e:
        print(f"\n[API 오류] {e}")
        return []

# =============================================================================
# [메인 로직]
# =============================================================================
def main():
    print("=" * 60)
    print("[*] 임베딩(Embedding) 생성 시작")
    print(f" - 입력 파일: {os.path.abspath(INPUT_FILE)}")
    
    if not os.path.exists(INPUT_FILE):
        print("[오류] 입력 파일을 찾을 수 없습니다.")
        return

    # 0. 이어하기(Resume) 준비: 기존 처리된 ID 확인
    processed_ids = set()
    if os.path.exists(OUTPUT_FILE):
        print(f"[*] 기존 결과 파일이 존재합니다. 이어하기를 준비합니다.")
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if "id" in record:
                        processed_ids.add(record["id"])
                except:
                    pass
        print(f" - 이미 처리된 청크 수: {len(processed_ids)}개")
    else:
        print(" - 기존 결과 파일이 없습니다. 새로 시작합니다.")

    # 1. 입력 파일 읽기 및 필터링
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    total_input_lines = len(lines)
    
    # 처리할 데이터 선별
    to_process_data = []
    
    # tqdm 없이 빠르게 필터링
    print("[*] 처리 대상 선별 중...")
    for line in lines:
        try:
            doc = json.loads(line)
            # 이미 처리된 ID면 스킵, 내용이 없으면 스킵
            if doc["id"] not in processed_ids and doc.get("content", "").strip():
                to_process_data.append(doc)
        except:
            continue
            
    total_tasks = len(to_process_data)
    skipped_count = total_input_lines - total_tasks
    
    print(f" - 전체 입력 청크: {total_input_lines}개")
    print(f" - 스킵됨 (완료/오류): {skipped_count}개")
    print(f" - 새로 처리할 청크: {total_tasks}개")
    
    if total_tasks == 0:
        print("[알림] 처리할 작업이 없습니다. 모든 데이터가 이미 임베딩되었습니다.")
        return

    print(f" - 배치 사이즈: {BATCH_SIZE} (예상 호출 횟수: {total_tasks // BATCH_SIZE + 1}회)")

    # 2. 배치 처리 및 저장 (Append Mode)
    success_count = 0
    
    # Ctrl+C 대응을 위한 try-except
    try:
        with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out: # 'a' 모드로 변경
            
            # 배치 단위 루프
            for i in tqdm(range(0, total_tasks, BATCH_SIZE), desc="Embedding"):
                
                # 현재 배치 데이터
                batch_data = to_process_data[i : i + BATCH_SIZE]
                batch_texts = [d["content"] for d in batch_data]
                
                if not batch_texts: continue

                # API 호출 (벡터 변환)
                vectors = get_embeddings_batch(batch_texts)
                
                # 결과 저장
                if len(vectors) == len(batch_data):
                    for doc, vector in zip(batch_data, vectors):
                        vector_record = {
                            "id": doc["id"],
                            "embedding": vector,
                            "content": doc["content"],
                            "fileId": doc["parent_doc_id"],
                            "metadata": doc["metadata"]
                        }
                        f_out.write(json.dumps(vector_record, ensure_ascii=False) + "\n")
                        success_count += 1
                    
                    # 파일 버퍼 비우기 (강제 종료 시 데이터 보존 확률 높임)
                    f_out.flush() 
                else:
                    print(f"\n[주의] 배치 처리 중 개수 불일치 발생")

                # API 속도 조절
                time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n[!] 사용자 요청에 의해 작업이 중단되었습니다 (Ctrl+C).")
        print(f"[!] 현재까지 진행된 내용은 '{OUTPUT_FILE}'에 저장되었습니다.")
        
    print("-" * 60)
    print(f"[종료] 임베딩 작업 마무리")
    print(f" - 이번 실행 저장된 벡터 수: {success_count}개")
    print(f" - 총 누적 결과 파일: {os.path.abspath(OUTPUT_FILE)}")
    print("=" * 60)

if __name__ == "__main__":
    main()