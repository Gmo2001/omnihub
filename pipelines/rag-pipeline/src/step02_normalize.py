import os
import json
import time
import glob
import warnings
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from tqdm import tqdm

# =============================================================================
# [설정 및 초기화]
# =============================================================================
warnings.filterwarnings("ignore")

PROJECT_ID = "jnu-rise-edu-147"
LOCATION = "us-central1"

# 경로 설정
# 경로 설정 (Project Root 기준)
DOCAI_DIR = r"data\docai_result"
EXISTING_META_FILE = r"data\metadata\omnihub_ai_metadata.jsonl"
CONTRACT_CONFIG_PATH = r"config\omnihub_contract_v0.1.json"
OUTPUT_FILE = r"data\processed\canonical_content.jsonl"

print("[State] Script Initializing...")

try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print("[State] Vertex AI Initialized.")
    model = GenerativeModel("gemini-1.5-flash")
    print("[State] Model Loaded: gemini-1.5-flash")
except Exception as e:
    print(f"[Error] Failed to initialize Vertex AI: {e}")
    exit()

def load_contract_config():
    print(f"[State] Loading config from: {CONTRACT_CONFIG_PATH}")
    if not os.path.exists(CONTRACT_CONFIG_PATH):
        print(f"[Error] Config file not found.")
        return None
    try:
        with open(CONTRACT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] Failed to parse JSON config: {e}")
        return None

# 설정 로드
contract_config = load_contract_config()
if not contract_config:
    exit()

print("[State] Config Loaded.")

# 규칙 추출
try:
    SCHEMA_RULES = contract_config['schema']
    BIZ_RULES = SCHEMA_RULES['business_rules']
    ENUMS = SCHEMA_RULES['enums']
    print("[State] Rules Extracted.")
except Exception as e:
    print(f"[Error] Failed to extract rules: {e}")
    exit()

# 프롬프트 템플릿
CONTRACT_PROMPT = f"""
파일명: {{filename}}
문서 내용을 분석하여 아래 'OmniHub Contract' 규칙에 맞는 JSON을 생성하라.

[분석 규칙]
1. summary: 핵심 내용 1~2문장 요약 (한국어)
2. securityLevel: 다음 기준에 따라 판단 ({ENUMS['securityLevel']})
   - High 키워드: {BIZ_RULES['security_high_keywords']}
   - Low 키워드: {BIZ_RULES['security_low_keywords']}
   - 위 키워드가 없으면 문맥에 따라 medium으로 판단.
3. department: 다음 부서 목록 중 하나 선택 ({BIZ_RULES['departments']})
4. tags: 검색용 영어 키워드 3~5개

[내용]
{{text}}
"""
print("[State] Prompt Ready.")

# =============================================================================
# [함수 정의]
# =============================================================================
def load_existing_metadata(filepath):
    print(f"[State] Loading metadata from {filepath}...")
    meta_map = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        record = data.get("structData", data)
                        meta_map[record.get("title")] = record
                    except: continue
        except Exception as e:
            print(f"[Warn] Failed to read metadata file: {e}")
    return meta_map

def extract_text_from_docai(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f).get("text", "")
    except: return ""

def get_original_filename(docai_path):
    parts = docai_path.split(os.sep)
    for p in parts:
        if p.lower().endswith(".pdf"): return p
    return "unknown.pdf"

def analyze_with_gemini(text, filename):
    try:
        safe_text = text[:4000]
        prompt = CONTRACT_PROMPT.format(filename=filename, text=safe_text)
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f" [Debug] Analysis Error for {filename}: {e}")
        return {"summary": "분석 실패", "securityLevel": "medium", "department": "General"}

def main():
    print("[*] 정규화(Canonicalization) 시작")
    print(f" - 적용 규칙: {contract_config['contractName']} (v{contract_config['version']})")
    
    meta_map = load_existing_metadata(EXISTING_META_FILE)
    print(f" - 기존 메타데이터: {len(meta_map)}건")
    
    json_files = glob.glob(os.path.join(DOCAI_DIR, "**/*.json"), recursive=True)
    print(f" - 처리할 DocAI 파일: {len(json_files)}건")

    if not json_files:
        print("[Warn] No input files found!")
        return

    success_count = 0
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:
        for json_path in tqdm(json_files, desc="Processing"):
            text = extract_text_from_docai(json_path)
            if not text: continue
            
            filename = get_original_filename(json_path)
            base_meta = meta_map.get(filename)
            
            if not base_meta:
                base_meta = {
                    "fileId": f"fil_{int(time.time())}",
                    "title": filename,
                    "virtualPath": "/Uncategorized",
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
            
            ai_meta = analyze_with_gemini(text, filename)
            
            canonical_doc = {
                "fileId": base_meta.get("fileId"),
                "title": base_meta.get("title", filename),
                "virtualPath": base_meta.get("virtualPath"),
                "source": base_meta.get("source", "upload"),
                "mimeType": base_meta.get("mimeType", "application/pdf"),
                "sizeBytes": base_meta.get("sizeBytes", 0),
                "content": text,
                "summary": ai_meta.get("summary"),
                "securityLevel": ai_meta.get("securityLevel"),
                "tags": ai_meta.get("tags", []),
                "department": ai_meta.get("department"),
                "docStatus": "approved",
                "ssot": True if ai_meta.get("securityLevel") == "high" else False,
                "createdAt": base_meta.get("createdAt"),
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "contractVersion": contract_config['version']
            }
            
            f_out.write(json.dumps(canonical_doc, ensure_ascii=False) + "\n")
            success_count += 1
            time.sleep(0.05)

    print("-" * 60)
    print(f"[완료] 총 {success_count}건 처리 완료 -> {OUTPUT_FILE}")

if __name__ == "__main__":
    print("[State] Calling main()...")
    try:
        main()
    except Exception as e:
        import traceback
        print(f"[FATAL ERROR] Main crashed: {e}")
        traceback.print_exc()