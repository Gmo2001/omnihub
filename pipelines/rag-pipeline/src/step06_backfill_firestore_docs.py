
# src/step06_backfill_firestore_docs.py
# 
# Usage Examples:
#   python src/step06_backfill_firestore_docs.py --dry-run
#   python src/step06_backfill_firestore_docs.py
#   python src/step06_backfill_firestore_docs.py --limit 10
#   python src/step06_backfill_firestore_docs.py --patch-missing-only --dry-run

import os
import json
import sys
import time
import argparse
import traceback
from tqdm import tqdm
from google.cloud import firestore

# ==== CONFIG ====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_RECORDS_FILE = os.path.join(BASE_DIR, "data", "processed", "doc_records.jsonl")
CFG_POL = os.path.join(BASE_DIR, "config", "publish_policy.json")
CFG_VEC = os.path.join(BASE_DIR, "config", "vector_search_config.json")

def parse_args():
    parser = argparse.ArgumentParser(description="Backfill Firestore Docs safely.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Firestore. Print samples only.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of records to process.")
    parser.add_argument("--collection", type=str, default="", help="Override target collection name.")
    parser.add_argument("--patch-missing-only", action="store_true", help="Only patch fields that are missing or empty in Firestore.")
    parser.add_argument("--sample-read", type=int, default=3, help="Number of existing docs to sample read before processing.")
    return parser.parse_args()

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def is_value_empty(val):
    if val is None: return True
    if isinstance(val, str) and not val.strip(): return True
    if isinstance(val, list) and not val: return True
    if isinstance(val, dict) and not val: return True
    return False

def get_patch_dict(incoming_doc, existing_doc):
    """
    Compare incoming `doc_record` with `existing_doc` (dict) from Firestore.
    Return a dict of fields to update. Return empty dict if no update needed.
    """
    patch = {}
    
    # Rules:
    # 1. name: if missing in existing, OR existing is 'unknown.pdf' and incoming is distinct
    ex_name = existing_doc.get("name")
    in_name = incoming_doc.get("name")
    if is_value_empty(ex_name) or (ex_name == "unknown.pdf" and in_name and in_name != "unknown.pdf"):
        if in_name: patch["name"] = in_name

    # 2. General fields: patch if missing/empty in existing
    # Target fields: driveUrl, folderPath, owner, textExcerpt, updatedAt
    target_fields = ["driveUrl", "folderPath", "owner", "textExcerpt", "updatedAt", "sizeKB", "status", "ext"]
    
    for f in target_fields:
        ex_val = existing_doc.get(f)
        in_val = incoming_doc.get(f)
        
        # If existing is empty, and incoming has value, patch it
        if is_value_empty(ex_val) and not is_value_empty(in_val):
            patch[f] = in_val
            
    # Special: aiSummary3
    ex_summ = existing_doc.get("aiSummary3")
    in_summ = incoming_doc.get("aiSummary3")
    # If existing has no valid summary (all empty or None), patch
    if not ex_summ or (isinstance(ex_summ, list) and all(x in ["-", ""] for x in ex_summ)):
        if in_summ: patch["aiSummary3"] = in_summ

    return patch

def main():
    try:
        args = parse_args()
        print(f"--- [Step 06] Backfill Firestore Docs ---")
        if args.dry_run:
            print(f"*** DRY RUN MODE: No writes will happen. ***")
        if args.patch_missing_only:
            print(f"*** PATCH MODE: Only filling missing/empty fields. Reading before writing. ***")

        # 1. Environment & Config
        pol_cfg = load_json(CFG_POL)
        vec_cfg = load_json(CFG_VEC)
        
        # Determine Project ID
        project_id = vec_cfg.get("project_id")
        if not project_id:
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        
        if not project_id:
            raise ValueError("No project_id found in config or env vars.")

        # Determine Collection
        col_docs = args.collection if args.collection else pol_cfg.get("firestore", {}).get("collection_docs", "omnihub_docs")

        # STARTUP LOGS
        print(f"\n[Environment Info]")
        print(f"  > Project ID       : {project_id}")
        print(f"  > Target Collection: {col_docs}")
        print(f"  > Input File       : {DOC_RECORDS_FILE}")
        print(f"  > Mode             : {'PATCH' if args.patch_missing_only else 'FULL UPSERT'}")
        
        # 2. Firestore Init & Health Check
        print(f"\n[Connection Check]")
        db = firestore.Client(project=project_id)
        
        # Health Check
        ping_ref = db.collection("zz_health").document("ping")
        if not args.dry_run:
            try:
                print("  > Writing to 'zz_health/ping'...", end=" ")
                ping_ref.set({"status": "WRITE_OK", "ts": firestore.SERVER_TIMESTAMP, "agent": "step06_backfill"})
                print("OK")
            except Exception as e:
                print("FAIL")
                raise RuntimeError(f"Health Check Write Failed: {e}")

        # Read Check
        try:
            print("  > Reading from 'zz_health/ping'...", end=" ")
            if ping_ref.get().exists: print(f"OK")
            else: print("MISSING (Read OK)")
        except Exception as e:
            raise RuntimeError(f"Health Check Read Failed: {e}")

        # 3. Load Data
        if not os.path.exists(DOC_RECORDS_FILE):
             raise FileNotFoundError(f"Input file missing: {DOC_RECORDS_FILE}")

        records = []
        limit_count = args.limit
        with open(DOC_RECORDS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line.strip()))
                    if limit_count > 0 and len(records) >= limit_count:
                        break
        
        print(f"\n[Processing] Loaded {len(records)} records (Limit={limit_count})")

        # Sample Read (if requested)
        if args.sample_read > 0:
            print(f"\n[Sample Read] Fetching {args.sample_read} existing docs...")
            exist_stream = db.collection(col_docs).limit(args.sample_read).stream()
            exist_docs = list(exist_stream)
            if not exist_docs:
                print("  > Collection is empty.")
            else:
                for d in exist_docs:
                    print(f"  > ID: {d.id} | Name: {d.get('name')} | Folder: {d.get('folderPath')}")

        # 4. Processing
        batch = db.batch()
        batch_limit = 400
        batch_count = 0
        total_commits = 0
        doc_updates_count = 0 # Updates queued/processed
        skipped_count = 0
        
        for doc in tqdm(records, desc="Processing"):
            doc_id = doc.get("id")
            if not doc_id: continue 
            
            doc_ref = db.collection(col_docs).document(doc_id)
            final_data = None
            
            if args.patch_missing_only:
                # Read specific doc
                # Note: getting 1-by-1 is slow. For 3000 docs it's okay (a few mins).
                # Optimization: could use db.get_all(refs) in chunks, but let's keep it simple for now.
                curr_snap = doc_ref.get()
                
                if not curr_snap.exists:
                    # Doc absent -> Full Insert needed
                    final_data = doc
                else:
                    # Check what needs patching
                    patch = get_patch_dict(doc, curr_snap.to_dict())
                    if patch:
                        final_data = patch
                    else:
                        skipped_count += 1
                        continue # No update needed
            else:
                # Full Upsert Mode
                final_data = doc
            
            # If here, we have data to write
            if args.dry_run:
                # Just sample print first few updates
                if doc_updates_count < 5:
                    print(f"  [DryRun Patch] ID={doc_id} -> {list(final_data.keys())}")
                doc_updates_count += 1
                continue

            # Queue write
            batch.set(doc_ref, final_data, merge=True)
            batch_count += 1
            doc_updates_count += 1
            
            if batch_count >= batch_limit:
                batch.commit()
                total_commits += 1
                batch = db.batch()
                batch_count = 0
        
        if batch_count > 0 and not args.dry_run:
            batch.commit()
            total_commits += 1
        
        print(f"\n[Done] Processed: {len(records)}")
        print(f"  > Updates/Inserts: {doc_updates_count}")
        print(f"  > Skipped (No Change): {skipped_count}")
        if not args.dry_run:
            print(f"  > Batches Committed: {total_commits}")

        # 5. Sanity Check (Post-Write)
        if not args.dry_run:
            print("\n[Sanity Check] Verifying Data...")
            res = list(db.collection(col_docs).limit(1).stream())
            if res: print(f"  > Check OK (ID: {res[0].id})")
            else: print(f"  > WARNING: Collection seems empty.")

    except Exception as e:
        print("\n[CRITICAL ERROR]")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
