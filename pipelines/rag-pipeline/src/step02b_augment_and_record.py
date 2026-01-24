
import os
import json
import time
import argparse
from tqdm import tqdm
from drive_meta_virtual import VirtualMetaGenerator

# Config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "canonical_content.jsonl")
OUTPUT_CANONICAL = os.path.join(BASE_DIR, "data", "processed", "canonical_with_drive.jsonl")
OUTPUT_DOC_RECORDS = os.path.join(BASE_DIR, "data", "processed", "doc_records.jsonl")
CONFIG_VIRTUAL = os.path.join(BASE_DIR, "config", "drive_meta_virtual.json")

def parse_args():
    parser = argparse.ArgumentParser(description="Augment metadata and create strict DocRecords.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of processed records (0=all)")
    return parser.parse_args()

def main():
    args = parse_args()
    print("--- [Step 02b] Augment & Strict Schema ---")
    
    if not os.path.exists(INPUT_FILE):
        print(f"[Error] Input file not found: {INPUT_FILE}")
        return

    gen = VirtualMetaGenerator(CONFIG_VIRTUAL)
    
    records_written = 0
    limit = args.limit
    
    with open(INPUT_FILE, "r", encoding="utf-8") as f_in, \
         open(OUTPUT_CANONICAL, "w", encoding="utf-8") as f_canon, \
         open(OUTPUT_DOC_RECORDS, "w", encoding="utf-8") as f_recs:
        
        # Read lines first to show progress bar correctly if limits are small
        # But for huge files, iterator is better. Let's stick to iterator with conditional break.
        
        lines_iter = tqdm(f_in, desc="Processing")
        
        for i, line in enumerate(lines_iter):
            if limit > 0 and records_written >= limit:
                break
                
            line = line.strip()
            if not line: continue
            
            try:
                doc = json.loads(line)
            except:
                continue

            # Keys for deterministic seed
            # Prioritize: doc.get("fileId") -> assume this is stable enough if it came from step02
            # But let's pass all info we have.
            f_id = doc.get("fileId", f"unknown_{i}")
            f_name = doc.get("title", "untitled")
            f_src = doc.get("source_uri", "") 
            
            # 1. Generate Virtual Meta (Enhanced)
            existing_meta_hint = {
                "department": doc.get("department"),
                "securityLevel": doc.get("securityLevel"),
                "tags": doc.get("tags", []),
                "sizeBytes": doc.get("sizeBytes")
            }
            
            v_meta = gen.generate(
                filename=f_name, 
                drive_file_id=f_id, # Use fileId as drive ID source
                source_uri=f_src,
                existing_meta=existing_meta_hint
            )
            
            # 2. Merge back to Canonical
            doc["drive_meta"] = v_meta
            f_canon.write(json.dumps(doc, ensure_ascii=False) + "\n")
            
            # 3. Create STRICT DocRecord
            # Enforce types and missing fields
            tags = doc.get("tags") or []
            if not isinstance(tags, list): tags = []
            
            concept_ids = [f"con_{t}" for t in tags]

            ai_summary = []
            orig_summ = doc.get("summary")
            if isinstance(orig_summ, str):
                ai_summary = [orig_summ]
            elif isinstance(orig_summ, list):
                ai_summary = orig_summ[:3]
            
            # Pad summary
            while len(ai_summary) < 3:
                ai_summary.append("-")
            
            content_snippet = doc.get("content", "")
            if len(content_snippet) > 200:
                content_snippet = content_snippet[:200]
            elif not content_snippet:
                content_snippet = "No content preview available."

            doc_record = {
                "id": str(f_id),
                "name": str(f_name),
                "driveUrl": str(v_meta["driveUrl"]),
                "folderPath": str(v_meta["folderPath"]),
                "actualPath": str(v_meta["actualPath"]),
                "owner": v_meta["owner"], # Already dict {name, email}
                "updatedAt": int(v_meta["updatedAt"]), # Force Int
                "sizeKB": int(v_meta["sizeKB"]), # Force Int
                "ext": str(v_meta["ext"]),
                "security": str(existing_meta_hint.get("securityLevel") or "medium"),
                "tags": tags,
                "conceptIds": concept_ids,
                "aiSummary3": ai_summary[:3], # Ensure length 3
                "textExcerpt": str(content_snippet),
                "status": str(v_meta["status"]),
                "relatedFolderPaths": v_meta["relatedFolderPaths"] # List[str]
            }
            
            f_recs.write(json.dumps(doc_record, ensure_ascii=False) + "\n")
            records_written += 1

    print(f"[Done] Processed {records_written} records.")
    print(f" -> {OUTPUT_CANONICAL}")
    print(f" -> {OUTPUT_DOC_RECORDS}")

if __name__ == "__main__":
    main()
