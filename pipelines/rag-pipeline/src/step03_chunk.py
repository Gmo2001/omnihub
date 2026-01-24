import os
import json
import glob
from tqdm import tqdm

# =============================================================================
# [설정 및 경로]
# =============================================================================
# 1. 입력: 정규화된 데이터 (Step 5 결과)
# 1. 입력: 정규화된 데이터
INPUT_CANONICAL_FILE = r"data\processed\canonical_content.jsonl"

# 2. 참조: Document AI 원본 결과
DOCAI_RAW_DIR = r"data\docai_result"

# 3. 설정: 청킹 정책
POLICY_FILE = r"config\chunking_policy.json"

# 4. 출력 파일들
OUTPUT_CHUNKS_FILE = r"data\processed\chunks.jsonl"
OUTPUT_MAP_FILE = r"data\processed\evidence_map.json"

# =============================================================================
# [Helper 1] Document AI 원본 매핑 및 페이지 범위 추출
# =============================================================================
def build_docai_path_map(docai_dir):
    """파일명 -> DocAI JSON 경로 매핑 테이블 생성"""
    print("[*] Document AI 원본 파일 인덱싱 중...")
    path_map = {}
    # 재귀적으로 모든 json 탐색
    json_files = glob.glob(os.path.join(docai_dir, "**/*.json"), recursive=True)
    
    for path in json_files:
        # 경로 예: .../계약서.pdf/0/output.json
        parts = path.split(os.sep)
        for p in parts:
            if p.lower().endswith(".pdf"):
                path_map[p] = path
                break
    print(f" - 원본 파일 매핑 완료: {len(path_map)}건")
    return path_map

def get_page_boundaries(docai_json_path):
    """
    DocAI JSON을 읽어서 각 페이지가 시작되는 글자 위치(Index)를 반환
    Returns: list of dict -> [{'page': 1, 'start': 0, 'end': 1500}, ...]
    """
    boundaries = []
    try:
        with open(docai_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        full_text_len = len(data.get('text', ''))
        pages = data.get('pages', [])
        
        for i, page in enumerate(pages):
            page_num = i + 1
            # DocAI의 textSegments 정보를 사용해 범위 확인
            segments = []
            if 'layout' in page and 'textAnchor' in page['layout']:
                segments = page['layout']['textAnchor'].get('textSegments', [])
            
            if segments:
                # 문자열 인덱스는 정수로 변환 필요
                start = int(segments[0].get('startIndex', 0))
                end = int(segments[-1].get('endIndex', full_text_len))
                boundaries.append({"page": page_num, "start": start, "end": end})
            else:
                # 정보가 없으면 이전 페이지 끝을 시작으로 간주 (Fallback)
                prev_end = boundaries[-1]['end'] if boundaries else 0
                boundaries.append({"page": page_num, "start": prev_end, "end": prev_end + 1})
                
    except Exception:
        pass # 에러 시 빈 리스트 반환 (페이지 매핑 실패 처리)
        
    return boundaries

def find_page_number(char_index, boundaries):
    """현재 글자 위치(Index)가 몇 페이지인지 찾기"""
    if not boundaries:
        return 1 # 정보 없으면 1페이지로 가정
    
    for b in boundaries:
        if b['start'] <= char_index < b['end']:
            return b['page']
    
    # 범위를 벗어나면 마지막 페이지 리턴
    return boundaries[-1]['page']

# =============================================================================
# [Helper 2] 청킹 로직 (Recursive Splitter)
# =============================================================================
def recursive_split(text, chunk_size, overlap, separators):
    """텍스트 분할 함수"""
    final_chunks = []
    if not text: return []

    separator = separators[-1]
    for sep in separators:
        if sep in text:
            separator = sep
            break
            
    splits = text.split(separator)
    current_chunk = []
    current_len = 0
    
    for split in splits:
        split_len = len(split)
        if current_len + split_len > chunk_size:
            if current_chunk:
                final_chunks.append(separator.join(current_chunk))
                # Overlap 처리 (간단하게 마지막 문단 유지)
                if overlap > 0 and len(current_chunk) > 1:
                    current_chunk = current_chunk[-1:]
                    current_len = len(current_chunk[0])
                else:
                    current_chunk = []
                    current_len = 0
        current_chunk.append(split)
        current_len += split_len
        
    if current_chunk:
        final_chunks.append(separator.join(current_chunk))
        
    return final_chunks

# =============================================================================
# [메인 로직]
# =============================================================================
def main():
    print("=" * 60)
    print("[*] 청킹 및 에비던스 매핑 통합 작업 시작")
    
    # 1. 정책 로드
    if os.path.exists(POLICY_FILE):
        with open(POLICY_FILE, 'r', encoding='utf-8') as f:
            policy = json.load(f)
    else:
        policy = {"chunk_size": 1000, "chunk_overlap": 200, "separators": ["\n\n", "\n", " "]}
    
    chunk_size = policy.get("chunk_size", 1000)
    overlap = policy.get("chunk_overlap", 200)
    separators = policy.get("separators", ["\n\n", "\n", " "])
    print(f" - 정책 설정: Size={chunk_size}, Overlap={overlap}")

    # 2. DocAI 원본 맵 생성 (페이지 찾기용)
    docai_map = build_docai_path_map(DOCAI_RAW_DIR)

    # 3. 데이터 처리
    if not os.path.exists(INPUT_CANONICAL_FILE):
        print(f"[오류] 정규화 파일이 없습니다: {INPUT_CANONICAL_FILE}")
        return

    evidence_map = {} # 결과 저장용 딕셔너리
    total_chunks = 0
    
    with open(INPUT_CANONICAL_FILE, 'r', encoding='utf-8') as f_in, \
         open(OUTPUT_CHUNKS_FILE, 'w', encoding='utf-8') as f_chunk_out:
        
        lines = f_in.readlines()
        print(f" - 처리할 문서 수: {len(lines)}개")
        
        for line in tqdm(lines, desc="Chunking & Mapping"):
            try:
                doc = json.loads(line)
            except: continue
            
            # 기본 정보 추출
            file_id = doc.get("fileId", "unknown")
            filename = doc.get("title", "unknown.pdf")
            content = doc.get("content", "")
            
            if not content: continue

            # A. 페이지 경계 정보 가져오기
            page_boundaries = []
            if filename in docai_map:
                page_boundaries = get_page_boundaries(docai_map[filename])

            # B. 청킹 수행
            chunks = recursive_split(content, chunk_size, overlap, separators)
            
            # C. 각 청크별 처리 (저장 + 페이지 매핑)
            # 현재 텍스트 상의 위치 추적용 변수
            current_char_idx = 0
            
            for idx, chunk_text in enumerate(chunks):
                chunk_id = f"{file_id}_ch{idx}"
                
                # 1. 페이지 찾기 (현재 시작 위치 기준)
                page_num = find_page_number(current_char_idx, page_boundaries)
                
                # 2. chunks.jsonl 기록 (벡터 DB용)
                chunk_record = {
                    "id": chunk_id,
                    "parent_doc_id": file_id,
                    "content": chunk_text,
                    "chunk_index": idx,
                    "metadata": {
                        "title": filename,
                        "securityLevel": doc.get("securityLevel"),
                        "department": doc.get("department"),
                        "tags": doc.get("tags", []),
                        "page": page_num, # 메타에도 페이지 정보 추가 (편의성)
                        "source_uri": doc.get("lineage", {}).get("raw_gcs_uri", "")
                    }
                }
                f_chunk_out.write(json.dumps(chunk_record, ensure_ascii=False) + "\n")
                
                # 3. evidence_map.json 기록 (UI 바로가기용)
                evidence_map[chunk_id] = {
                    "fileId": file_id,
                    "filename": filename,
                    "page": page_num,
                    "snippet": chunk_text[:50] + "..." # 확인용 스니펫
                }
                
                # 다음 청크 위치 계산 (Overlap 고려)
                chunk_len = len(chunk_text)
                current_char_idx += (chunk_len - overlap)
                if current_char_idx < 0: current_char_idx = 0 # 방어코드
                
                total_chunks += 1

    # 4. 매핑 파일 저장
    with open(OUTPUT_MAP_FILE, 'w', encoding='utf-8') as f_map_out:
        json.dump(evidence_map, f_map_out, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"[완료] 모든 작업이 끝났습니다.")
    print(f" 1. 청크 데이터: {os.path.abspath(OUTPUT_CHUNKS_FILE)} (총 {total_chunks}개)")
    print(f" 2. 에비던스 맵: {os.path.abspath(OUTPUT_MAP_FILE)}")
    print("=" * 60)

if __name__ == "__main__":
    main()