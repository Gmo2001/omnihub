# bundle_project_to_txt_v3.py
# Python 3.9+

import os
import sys
import json
import hashlib
import random
import re
from pathlib import Path
from datetime import datetime
from collections import Counter
from tqdm import tqdm
import tkinter as tk
from tkinter import filedialog

# =============================================================================
# [1] 사용자 설정
# =============================================================================
# 자동 경로 설정
current_file_path = Path(__file__).resolve()
project_base_dir = current_file_path.parent.parent  # src의 상위 폴더 (bundle_project_to_txt)
DEFAULT_OUTPUT_DIR = project_base_dir / "data"

ROOT_DIR = None  # 실행 시 폴더 선택 창이 뜹니다. 필요하다면 여기에 경로를 직접 적어도 됩니다.
OUTPUT_DIR = DEFAULT_OUTPUT_DIR

BUNDLE_FILENAME = "project_bundle.txt"
TREE_FILENAME = "project_tree.txt"
META_FILENAME = "project_meta.json"

# 일반 파일 크기 제한 (본문 포함 시)
MAX_BYTES_PER_FILE = 1_000_000   # 1MB
HEAD_BYTES = 650_000
TAIL_BYTES = 350_000

# 번들 총 크기 제한
MAX_TOTAL_BYTES = 120_000_000  # 120MB

# 트리 설정
TREE_MAX_FILES_PER_DIR = 80
TREE_SUMMARY_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico", ".pdf"}

# Data 폴더 설정
DATA_LARGE_THRESHOLD_BYTES = 1 * 1024**3  # 1GB
INLINE_HEAD_BYTES = 40_000
INLINE_TAIL_BYTES = 10_000

# 샘플링 설정
NORMAL_SAMPLES = 2
SUSPECT_SAMPLES = 2
LARGEST_SAMPLES = 1

# =============================================================================
# [2] 제외/포함 규칙
# =============================================================================
EXCLUDE_DIR_NAMES = {
    ".git", ".svn", ".hg",
    "node_modules", ".next", "dist", "build", "out",
    "venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".cache", ".idea", ".vscode",
    "coverage", ".turbo", ".parcel-cache",
    "target",
}

EXCLUDE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
    ".pdf", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".flac",
    ".exe", ".dll", ".so", ".dylib",
    ".bin", ".dat",
    ".pyc", ".pyo",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".class", ".jar",
    ".pkl", ".pickle",
}

EXCLUDE_FILENAMES = {
    ".env", ".env.local", ".env.development", ".env.production",
    "id_rsa", "id_ed25519",
}

SENSITIVE_NAME_KEYWORDS = (
    "service_account", "sa-key", "private_key", "credential", "credentials",
    "apikey", "api_key", "secret", "token"
)

# 텍스트로 취급할 확장자
TEXT_EXT_ALLOWLIST = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".php", ".rb", ".swift",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst",
    ".sql", ".graphql", ".gql",
    ".html", ".css", ".scss",
    ".sh", ".bash", ".zsh", ".ps1",
}

TEXT_NAME_ALLOWLIST = {"dockerfile", "makefile", "readme", "license", "pipfile", "pyproject.toml", ".gitignore", ".dockerignore", "requirements.txt"}

# 샘플링용 확장자
SAMPLE_EXT_ALLOWLIST = {".json", ".jsonl", ".txt", ".md", ".yaml", ".yml", ".csv"}

# 인라인 마스킹 타겟 키
MASK_KEYS = [
    "private_key", "api_key", "apikey", "access_token", "refresh_token", "token", "secret", "credential"
]

# =============================================================================
# [3] 유틸
# =============================================================================
def is_probably_binary(path: Path, sniff_bytes: int = 4096) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
        if b"\x00" in chunk:
            return True
        bad = 0
        for b in chunk:
            if b < 0x09 or (0x0E <= b < 0x20):
                bad += 1
        return bad > 50
    except Exception:
        return True

def safe_relpath(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")

def is_child_of_data(p: Path, root: Path) -> bool:
    # root/data/xxx 형태인지 확인
    rel = safe_relpath(p, root)
    return rel.startswith("data/")

def should_exclude_path(path: Path, root: Path = None) -> (bool, str):
    # root가 주어지면 data 폴더 체크
    if root and is_child_of_data(path, root):
        return True, "excluded_data_folder"

    name_lower = path.name.lower()
    if path.is_dir():
        if path.name in EXCLUDE_DIR_NAMES:
            return True, f"excluded_dir:{path.name}"
        return False, ""

    if path.name in EXCLUDE_FILENAMES:
        return True, f"excluded_filename:{path.name}"

    # 민감 키워드 체크
    if any(k in name_lower for k in SENSITIVE_NAME_KEYWORDS):
        return True, "excluded_sensitive_name_keyword"

    ext = path.suffix.lower()
    if ext in EXCLUDE_EXTS:
        return True, f"excluded_ext:{ext}"

    return False, ""

def is_text_candidate(path: Path) -> bool:
    ext = path.suffix.lower()
    name_lower = path.name.lower()
    if name_lower in TEXT_NAME_ALLOWLIST:
        return True
    if ext in TEXT_EXT_ALLOWLIST:
        return True
    if path.name in {"Dockerfile", "Makefile"}:
        return True
    return False

def sha256_of_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def trim_content_bytes(raw: bytes, head_limit: int, tail_limit: int) -> (bytes, bool):
    if len(raw) <= (head_limit + tail_limit):
        return raw, False
    head_bytes = raw[:head_limit]
    tail_bytes = raw[-tail_limit:]
    marker = (
        b"\n\n"
        b"----- [TRUNCATED] file too large; showing HEAD and TAIL only -----\n\n"
    )
    return head_bytes + marker + tail_bytes, True

def simple_masking(text: str) -> str:
    # "key": "value" or key: value pattern
    # value doesn't contain " ideally
    for key in MASK_KEYS:
        # JSON style: "key": "..."
        pattern_json = f'"{key}"\\s*:\\s*"([^"]+)"'
        text = re.sub(pattern_json, f'"{key}": "***"', text, flags=re.IGNORECASE)
        
        # YAML keys: key: ...
        # This is harder to match perfectly without parsing, doing simple check
        # pattern_yaml = f'{key}\\s*:\\s*(\\S+)'
        # text = re.sub(pattern_yaml, f'{key}: ***', text, flags=re.IGNORECASE)
    return text

def remove_base64_and_large_fields(text: str, is_json_candidate: bool) -> (str, bool, int):
    """
    Returns: (processed_text, binary_stripped_bool, stripped_count)
    """
    stripped = False
    count = 0
    
    # Target keys for removal
    OMIT_KEYS = {
        "content", "inlineObject", "inlineObjects", "rawDocument", "document", 
        "pdfBytes", "image", "images", "blob", "bytes", "binary", "dataUri", 
        "base64", "pageImage", "pageImages"
    }

    # Helper recursive function for JSON
    def clean_json_obj(obj):
        nonlocal stripped, count
        if isinstance(obj, dict):
            for k, v in list(obj.items()): # list for safe modification
                if k in OMIT_KEYS:
                     # Check if it looks like base64 or large string
                     if isinstance(v, str):
                         if len(v) > 50: # Assume small values are not base64 blobs usually
                             obj[k] = "<base64/binary omitted>"
                             stripped = True
                             count += 1
                     elif isinstance(v, list) or isinstance(v, dict):
                         # Recursively clean or just omitted if it's the target key? 
                         # Requirement says "replace value with <omitted>". 
                         # But let's check content specifically for text.
                         if k == "content":
                             # Special handled: only if long and high base64 density
                             if isinstance(v, str) and len(v) > 2000:
                                 # Simple base64 check: A-Za-z0-9+/=
                                 # Just check length for now as per prompt "2000자 이상"
                                 obj[k] = "<base64 omitted (length)>"
                                 stripped = True
                                 count += 1
                         else:
                             # Other keys: direct replacement
                             obj[k] = "<omitted>"
                             stripped = True
                             count += 1
                else:
                    clean_json_obj(v)
        elif isinstance(obj, list):
            for item in obj:
                clean_json_obj(item)

    # 1. Try JSON parsing
    if is_json_candidate:
        try:
            data = json.loads(text)
            clean_json_obj(data)
            if stripped:
                return json.dumps(data, ensure_ascii=False, indent=2), True, count
            return text, False, 0
        except:
            pass # Fallback to regex

    # 2. Text Pattern Fallback
    # Pattern: "content":"<very long>"
    # We want to match "key" : "value" where value is > 2000 chars
    # Regex for general large string value in JSON-like structure
    # This is tricky with regex. Let's try simple specific patterns for fail-safe.
    
    # "content":"..."
    # "data":"..."
    # "image":{"content":"..."}
    
    patterns = [
        r'("content"\s*:\s*")([^"]{2000,})(")',
        r'("data"\s*:\s*")([^"]{2000,})(")',
        r'("image"\s*:\s*\{\s*"content"\s*:\s*")([^"]{2000,})(")',
    ]
    
    processed_text = text
    for pat in patterns:
        def repl(m):
            nonlocal stripped, count
            stripped = True
            count += 1
            return m.group(1) + "<base64 omitted>" + m.group(3)
            
        processed_text = re.sub(pat, repl, processed_text, flags=re.DOTALL)

    return processed_text, stripped, count

# =============================================================================
# [4] Data 폴더 분석 및 샘플링
# =============================================================================
def analyze_data_folder(root: Path):
    data_dir = root / "data"
    if not data_dir.exists() or not data_dir.is_dir():
        return []

    print("[INFO] Analyzing data folder...")
    datasets = []
    
    # data/ 하위 1레벨 순회
    for entry in data_dir.iterdir():
        if not entry.is_dir():
            continue
        
        ds_info = {
            "path": safe_relpath(entry, root),
            "size_bytes": 0,
            "file_count": 0,
            "top_exts": {},
            "status": "small",
            "samples": {
                "normal": [],
                "suspect": [],
                "largest": []
            }
        }

        # Scan folder
        ext_counter = Counter()
        file_list = []  # save potential candidates for sampling
        
        total_size = 0
        total_files = 0
        
        # Walk recursively
        for r, ds, fs in os.walk(entry):
            # exclude dirs
            ds[:] = [d for d in ds if d not in EXCLUDE_DIR_NAMES]
            
            for f in fs:
                fp = Path(r) / f
                if fp.name in EXCLUDE_FILENAMES:
                    continue
                # Sensitive name check for sampling candidates
                is_sensitive = any(k in f.lower() for k in SENSITIVE_NAME_KEYWORDS)
                
                try:
                    stat = fp.stat()
                    fsize = stat.st_size
                except:
                    fsize = 0
                
                total_size += fsize
                total_files += 1
                ext = fp.suffix.lower() or "(no_ext)"
                ext_counter[ext] += 1

                # If sensitive, don't add to sampling candidates
                if is_sensitive:
                    continue
                # Extension check for sampling
                if ext in SAMPLE_EXT_ALLOWLIST:
                    file_list.append((fp, fsize))
        
        ds_info["size_bytes"] = total_size
        ds_info["file_count"] = total_files
        
        # Top exts
        top = ext_counter.most_common(8)
        ds_info["top_exts"] = {k: v for k, v in top}
        # Status
        if total_size >= DATA_LARGE_THRESHOLD_BYTES:
            ds_info["status"] = "large"
        
        # Sampling if large
        if ds_info["status"] == "large" and file_list:
            # 1. Largest
            file_list.sort(key=lambda x: x[1], reverse=True)
            if file_list:
                largest_files = file_list[:LARGEST_SAMPLES]
                ds_info["samples"]["largest"] = [safe_relpath(f[0], root) for f in largest_files]

            # 2. Suspect
            suspects = []
            # Priority 1: keywords
            suspect_keywords = ["error", "fail", "failed", "empty", "null", "corrupt", "broken"]
            s_cand = [x for x in file_list if any(k in x[0].name.lower() for k in suspect_keywords)]
            # Priority 2: 0 bytes
            if len(s_cand) < SUSPECT_SAMPLES:
                s_cand.extend([x for x in file_list if x[1] == 0])
            # Priority 3: < 1KB
            if len(s_cand) < SUSPECT_SAMPLES:
                s_cand.extend([x for x in file_list if 0 < x[1] < 1024])
            
            # dedup
            seen_s = set()
            uniq_suspects = []
            for item in s_cand:
                if item[0] not in seen_s:
                    seen_s.add(item[0])
                    uniq_suspects.append(item)
            
            # pick random if too many
            if len(uniq_suspects) > SUSPECT_SAMPLES:
                chosen_s = random.sample(uniq_suspects, SUSPECT_SAMPLES)
            else:
                chosen_s = uniq_suspects
            
            ds_info["samples"]["suspect"] = [safe_relpath(f[0], root) for f in chosen_s]

            # 3. Normal
            # remove already chosen
            chosen_paths = set()
            for p in ds_info["samples"]["largest"]: chosen_paths.add(p)
            for p in ds_info["samples"]["suspect"]: chosen_paths.add(p)

            remaining = [x for x in file_list if safe_relpath(x[0], root) not in chosen_paths and x[1] > 0]
            
            if len(remaining) > NORMAL_SAMPLES:
                chosen_n = random.sample(remaining, NORMAL_SAMPLES)
            else:
                chosen_n = remaining
            ds_info["samples"]["normal"] = [safe_relpath(f[0], root) for f in chosen_n]
            
            print(f"- {ds_info['path']} [LARGE]: sampled {len(ds_info['samples']['largest'])+len(ds_info['samples']['suspect'])+len(ds_info['samples']['normal'])} files")

        else:
             print(f"- {ds_info['path']}: {total_files} files, {ds_info['size_bytes']/(1024**3):.2f} GB ({ds_info['status']})")

        datasets.append(ds_info)
    
    return datasets

# =============================================================================
# [5] 트리 생성
# =============================================================================
def summarize_dir_files(dir_path: Path):
    ext_counter = Counter()
    total_files = 0
    try:
        for entry in dir_path.iterdir():
            if entry.is_file():
                total_files += 1
                ext_counter[entry.suffix.lower() or "(no_ext)"] += 1
    except Exception:
        return total_files, ext_counter
    return total_files, ext_counter

def build_tree(root: Path, datasets_info: list) -> str:
    lines = []
    lines.append(root.name + "/")

    # dataset path -> status lookup
    ds_map = {d["path"]: d["status"] for d in datasets_info}

    def walk(dir_path: Path, prefix: str = ""):
        try:
            entries = list(dir_path.iterdir())
        except Exception:
            return

        dirs = sorted([e for e in entries if e.is_dir()], key=lambda x: x.name.lower())
        files = sorted([e for e in entries if e.is_file()], key=lambda x: x.name.lower())

        for i, d in enumerate(dirs):
            is_last_dir = (i == len(dirs) - 1 and len(files) == 0)
            branch = "└── " if is_last_dir else "├── "
            next_prefix = prefix + ("    " if is_last_dir else "│   ")

            if d.name in EXCLUDE_DIR_NAMES:
                lines.append(prefix + branch + d.name + "/ [excluded]")
                continue
            
            # Check if this dir is a large dataset
            rel_p = safe_relpath(d, root)
            if rel_p in ds_map:
                status = ds_map[rel_p]
                if status == "large":
                    lines.append(prefix + branch + d.name + "/ [large] (children elided; see DATA SUMMARY)")
                    continue # Do not recurse
                else:
                    # just separate data folder, but recurse limitation logic for data?
                    # "data 내부는 1레벨까지만 펼치고 그 아래는 요약"
                    # If this is inside data but not caught above (e.g. data/small_set)
                    # The instruction says "Use one line summary for deep structure"
                    # For simplicity, if it's a known dataset, we recurse but maybe limit depth?
                    # The prompt implies: data -> dataset level is shown. Below dataset level -> elide.
                    # So actually for ALL datasets (large or small) under data/, we should probably elide children 
                    # OR distinct logic. Prompt: "1GB 이상(large) 데이터 세트는 ... [large]... (children elided)"
                    # "data 하위 깊은 구조는 트리 폭발 방지를 위해, data 내부는 1레벨까지만 펼치고 그 아래는 요약 한 줄"
                    # Which implies all data subfolders should be elided in tree?
                    # Let's elide all children of any folder that is a direct child of 'data/'.
                    lines.append(prefix + branch + d.name + "/ (children elided; see DATA SUMMARY)")
                    continue

            lines.append(prefix + branch + d.name + "/")
            walk(d, next_prefix)

        # File display
        if len(files) > TREE_MAX_FILES_PER_DIR:
            total_files, ext_counter = summarize_dir_files(dir_path)
            highlight = []
            for ext in sorted(TREE_SUMMARY_EXTS):
                if ext in ext_counter:
                    highlight.append(f"{ext}:{ext_counter[ext]}")
            others = [(k, v) for k, v in ext_counter.most_common(6) if k not in TREE_SUMMARY_EXTS]
            other_txt = ", ".join([f"{k}:{v}" for k, v in others])
            summary_parts = [f"files:{total_files}"]
            if highlight: summary_parts.append("highlight(" + ", ".join(highlight[:8]) + ")")
            if other_txt: summary_parts.append("top(" + other_txt + ")")

            branch = "└── " if len(dirs) == 0 else "├── "
            lines.append(prefix + branch + "[files elided] " + " | ".join(summary_parts))
            return

        for j, f in enumerate(files):
            is_last = (j == len(files) - 1)
            branch = "└── " if (len(dirs) == 0 and is_last) else "├── "
            lines.append(prefix + branch + f.name)

    walk(root)
    return "\n".join(lines) + "\n"

# =============================================================================
# [6] 메인
# =============================================================================
def run_bundler(target_path=None, output_path=None):
    # Default to globals if not provided
    if target_path is None:
        target_path = ROOT_DIR
    if output_path is None:
        output_path = OUTPUT_DIR

    # target_path이 설정되지 않았으면 폴더 선택 창 띄우기
    if not target_path:
        print("[INFO] 수집할 프로젝트 폴더를 선택하세요...")
        try:
            root_tk = tk.Tk()
            root_tk.withdraw()  # 메인 윈도우 숨김
            root_tk.attributes('-topmost', True)  # 창을 맨 앞으로
            
            selected_path = filedialog.askdirectory(
                title="수집할 프로젝트 폴더 선택",
                initialdir=os.getcwd()
            )
            root_tk.destroy()
            
            if selected_path:
                target_path = selected_path
            else:
                print("[INFO] 폴더 선택이 취소되었습니다.")
                sys.exit(0)
        except Exception as e:
            print(f"[ERROR] 폴더 선택 창 오류: {e}")
            sys.exit(1)

    root = Path(target_path).resolve()
    
    # Patch C: Timestamped Output Folder
    # ai_export 대신 루트 폴더명 사용
    timestamp_folder_name = f"{root.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # Use output_dir based on user setting or current dir
    base_out = Path(output_path).resolve() if output_path else Path(".").resolve()
    out_dir = base_out / timestamp_folder_name
    out_dir.mkdir(parents=True, exist_ok=True) # Create folder

    # Files are now inside out_dir without timestamp suffix needed (folder has ts), 
    # but maintaining TS in filename is allowed/fine. Let's keep it clean or TS?
    # Prompt says: "출력 파일명은 기존 규칙을 유지하되(또는 타임스탬프를 파일명에 붙여도 무방)"
    # Let's keep them as fixed names inside the unique folder for simplicity if possible?
    # Actually User Prompt v3 added TS to filename. User Patch C says "project_tree.txt" inside.
    # Let's use clean names inside the timestamp folder.
    
    tree_path = out_dir / TREE_FILENAME
    bundle_path = out_dir / BUNDLE_FILENAME
    meta_path = out_dir / META_FILENAME

    if not root.exists() or not root.is_dir():
        print(f"[ERROR] ROOT_DIR is invalid: {root}")
        sys.exit(1)

    # 1. Analyze Data
    datasets_info = analyze_data_folder(root)

    # 2. Build Tree
    tree_text = build_tree(root, datasets_info)
    tree_path.write_text(tree_text, encoding="utf-8")

    # Meta Init
    meta = {
        "root_dir": str(root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {
            "max_bytes_per_file": MAX_BYTES_PER_FILE,
            "max_total_bytes": MAX_TOTAL_BYTES,
        },
        "data_sets": datasets_info,
        "files_included": [],
        "files_excluded": [],
        "stats": {
            "included_count": 0,
            "excluded_count": 0,
            "truncated_count": 0,
            "binary_skipped_count": 0,
            "non_text_skipped_count": 0,
            "bundle_bytes_written": 0,
        }
    }

    # 3. Collect Normal Files
    all_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
        
        # Check if we are inside data/ folder -> skip recursion for files
        # Because we already handled data in analyze_data_folder and we don't want to include them in bundle
        rel_dir = safe_relpath(Path(dirpath), root)
        if rel_dir.startswith("data/") or rel_dir == "data":
            # Don't collect files from data folder for the main bundle
            continue

        for fn in filenames:
            all_files.append(Path(dirpath) / fn)
    
    all_files = sorted(all_files, key=lambda p: str(p).lower())

    # Excluded Stats for normal files
    exclude_reason_counter = Counter()
    # (We only count exlcuded reasons for files we consider processing, i.e. not in data/)
    
    total_written = 0
    try:
        with bundle_path.open("w", encoding="utf-8", errors="replace") as out:
            # Header
            header_lines = []
            header_lines.append("ROOT MAP:")
            header_lines.append(f"- root = {str(root)}")
            header_lines.append("")
            header_lines.append("TREE:")
            header_lines.append(tree_text.rstrip())
            header_lines.append("")
            header_lines.append("EXCLUDED SUMMARY (existence only; contents not included):")
            # Proactive check for exclusion to fill summary
            for p in all_files:
                excluded, reason = should_exclude_path(p, root)
                if excluded:
                    exclude_reason_counter[reason] += 1
                elif not is_text_candidate(p):
                    exclude_reason_counter["non_text"] += 1
                elif is_probably_binary(p):
                    exclude_reason_counter["binary"] += 1
            
            for reason, cnt in exclude_reason_counter.most_common():
                header_lines.append(f"- {reason}: {cnt} files")
            header_lines.append("")
            
            # DATA SUMMARY
            header_lines.append("DATA SUMMARY:")
            if not datasets_info:
                header_lines.append("(No data folder found or empty)")
            else:
                for ds in datasets_info:
                    sz_gb = ds['size_bytes'] / (1024**3)
                    sz_mb = ds['size_bytes'] / (1024**2)
                    sz_str = f"{sz_gb:.1f}GB" if sz_gb >= 1 else f"{sz_mb:.1f}MB"
                    
                    top_s = ",".join([f"{k}:{v}" for k,v in ds['top_exts'].items()])
                    header_lines.append(f"{ds['path']} | size={sz_str} | files={ds['file_count']} | status={ds['status']} | top_exts={top_s}")
            header_lines.append("")

            # SAMPLE PICK
            header_lines.append("SAMPLE PICK (for large datasets):")
            for ds in datasets_info:
                if ds['status'] == 'large':
                    header_lines.append(f"SAMPLE PICK ({ds['path']})")
                    if ds['samples']['normal']:
                        header_lines.append(f"- normal: {', '.join(ds['samples']['normal'])}")
                    if ds['samples']['suspect']:
                        header_lines.append(f"- suspect: {', '.join(ds['samples']['suspect'])}")
                    if ds['samples']['largest']:
                        header_lines.append(f"- largest: {', '.join(ds['samples']['largest'])}")
                    header_lines.append("")
            
            header_lines.append("=" * 80)
            header_lines.append("")
            out.write("\n".join(header_lines) + "\n")
            total_written = len(("\n".join(header_lines) + "\n").encode("utf-8", errors="replace"))

            # INLINE SAMPLES
            # Iterate datasets, check samples, read and inline
            for ds in datasets_info:
                if ds['status'] != 'large': continue
                
                # Merge all sample lists
                all_s = ds['samples']['normal'] + ds['samples']['suspect'] + ds['samples']['largest']
                # dedup
                all_s = sorted(list(set(all_s)))
                
                for s_rel in all_s:
                    s_path = root / s_rel
                    if not s_path.exists(): continue
                    
                    # only inline allowlist extensions
                    if s_path.suffix.lower() not in SAMPLE_EXT_ALLOWLIST:
                        continue
                        
                    try:
                        raw = s_path.read_bytes()
                        raw2, truncated = trim_content_bytes(raw, INLINE_HEAD_BYTES, INLINE_TAIL_BYTES)
                        
                        try:
                            text = raw2.decode("utf-8")
                        except:
                            text = raw2.decode("utf-8", errors="replace")
                        
                        # Patch A: Remove base64/large fields BEFORE masking
                        is_json = s_path.suffix.lower() in {".json", ".jsonl"}
                        text, binary_stripped, stripped_count = remove_base64_and_large_fields(text, is_json)
                        
                        # Existing Masking
                        text = simple_masking(text)
                        
                        sh = []
                        sh.append(f"---- INLINE SAMPLE: {s_rel} ----")
                        sh.append(f"SIZE_BYTES_ORIGINAL: {len(raw)}")
                        sh.append(f"TRUNCATED: {'yes' if truncated else 'no'}")
                        if binary_stripped:
                            sh.append(f"BINARY_STRIPPED: yes")
                            sh.append(f"STRIPPED_FIELDS_COUNT: {stripped_count}")
                        
                        # Split head/tail if marker exists
                        marker_str = "----- [TRUNCATED] file too large; showing HEAD and TAIL only -----"
                        if marker_str in text:
                            parts = text.split(marker_str)
                            head_t = parts[0].strip()
                            tail_t = parts[1].strip() if len(parts) > 1 else ""
                            sh.append("----- BEGIN HEAD -----")
                            sh.append(head_t)
                            sh.append("----- END HEAD -----")
                            sh.append(f"\n... (truncated bytes) ...\n")
                            sh.append("----- BEGIN TAIL -----")
                            sh.append(tail_t)
                            sh.append("----- END TAIL -----")
                        else:
                            sh.append("----- BEGIN CONTENT -----")
                            sh.append(text)
                            sh.append("----- END CONTENT -----")
                        
                        sh.append("\n")
                        out.write("\n".join(sh))
                        
                    except Exception as e:
                        out.write(f"\n[ERROR Reading Sample {s_rel}: {e}]\n")

            # Main File Content Loop
            for p in tqdm(all_files, desc="Bundling files", unit="file"):
                rel = safe_relpath(p, root)
                
                # Check exclusion again for actual processing
                excluded, reason = should_exclude_path(p, root)
                if excluded:
                    meta["files_excluded"].append({"path": rel, "reason": reason})
                    meta["stats"]["excluded_count"] += 1
                    continue
                
                if not is_text_candidate(p):
                    meta["files_excluded"].append({"path": rel, "reason": "non_text"})
                    meta["stats"]["excluded_count"] += 1
                    meta["stats"]["non_text_skipped_count"] += 1
                    continue
                
                if is_probably_binary(p):
                    meta["files_excluded"].append({"path": rel, "reason": "binary"})
                    meta["stats"]["excluded_count"] += 1
                    meta["stats"]["binary_skipped_count"] += 1
                    continue

                try:
                    raw = p.read_bytes()
                except Exception as e:
                    meta["files_excluded"].append({"path": rel, "reason": f"read_error:{type(e).__name__}"})
                    meta["stats"]["excluded_count"] += 1
                    continue

                raw2, truncated = trim_content_bytes(raw, HEAD_BYTES, TAIL_BYTES)
                if truncated:
                    meta["stats"]["truncated_count"] += 1

                try:
                    text = raw2.decode("utf-8")
                except Exception:
                    text = raw2.decode("utf-8", errors="replace")

                block_header = []
                block_header.append(f"===== FILE: {rel} =====")
                block_header.append(f"SIZE_BYTES_ORIGINAL: {len(raw)}")
                block_header.append(f"SIZE_BYTES_EMITTED: {len(raw2)}")
                block_header.append(f"SHA256_ORIGINAL: {sha256_of_bytes(raw)}")
                block_header.append(f"TRUNCATED: {'yes' if truncated else 'no'}")
                block_header.append("----- BEGIN CONTENT -----")

                block = "\n".join(block_header) + "\n" + text + "\n----- END CONTENT -----\n\n"
                block_bytes = len(block.encode("utf-8", errors="replace"))

                if MAX_TOTAL_BYTES is not None and (total_written + block_bytes) > MAX_TOTAL_BYTES:
                    out.write("===== STOP =====\n")
                    out.write("Bundle reached MAX_TOTAL_BYTES limit. Remaining files were not included.\n")
                    meta["files_excluded"].append({"path": rel, "reason": "bundle_size_limit_reached"})
                    meta["stats"]["excluded_count"] += 1
                    break

                out.write(block)
                total_written += block_bytes

                meta["files_included"].append({
                    "path": rel,
                    "size_bytes_original": len(raw),
                    "size_bytes_emitted": len(raw2),
                    "sha256_original": sha256_of_bytes(raw),
                    "truncated": truncated
                })
                meta["stats"]["included_count"] += 1

            meta["stats"]["bundle_bytes_written"] = total_written

    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user (Ctrl+C). Saving meta and exiting...")
    
    # Save Meta
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[DONE]")
    print(f"- Output Dir: {str(out_dir)}")
    print(f"- Tree:   {str(tree_path.resolve())}")
    print(f"- Bundle: {str(bundle_path.resolve())}")
    print(f"- Meta:   {str(meta_path.resolve())}")

if __name__ == "__main__":
    run_bundler()
