# src/step05_publish.py
import os, json, time, sys
from tqdm import tqdm

from google.cloud import aiplatform
from google.cloud import firestore
from google.cloud.aiplatform.matching_engine import matching_engine_index_endpoint as me

# ==== CONFIG ====
# [필독] 실행 시점에 환경 변수로 오버라이드 가능 (기본값: firestore_only) -> 할때마다 PUBLISH_MODE 설정 바꿔야 한다는 이야기
PUBLISH_MODE = os.environ.get("PUBLISH_MODE", "firestore_only") # "firestore_only" or "both"
# ================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_VEC = os.path.join(BASE_DIR, "config", "vector_search_config.json")
CFG_POL = os.path.join(BASE_DIR, "config", "publish_policy.json")

CHUNKS_FILE = os.path.join(BASE_DIR, "data", "processed", "chunks.jsonl")
EMB_FILE    = os.path.join(BASE_DIR, "data", "processed", "embeddings.jsonl")
EVI_FILE    = os.path.join(BASE_DIR, "data", "processed", "evidence_map.json")

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: 
                continue
            yield json.loads(line)

def get_or_create_index(cfg):
    indexes = aiplatform.MatchingEngineIndex.list(
        filter=f'display_name="{cfg["index_display_name"]}"'
    )
    if indexes:
        return indexes[0]

    return aiplatform.MatchingEngineIndex.create_tree_ah_index(
        display_name=cfg["index_display_name"],
        contents_delta_uri=None,
        dimensions=cfg["dimensions"],
        approximate_neighbors_count=cfg["approximate_neighbors_count"],
        leaf_node_embedding_count=500,
        leaf_nodes_to_search_percent=7,
        index_update_method="STREAM_UPDATE",
        distance_measure_type=aiplatform.matching_engine.matching_engine_index_config.DistanceMeasureType.COSINE_DISTANCE,
        shard_size=cfg["shard_size"],
    )

def get_or_create_endpoint(cfg):
    eps = aiplatform.MatchingEngineIndexEndpoint.list(
        filter=f'display_name="{cfg["endpoint_display_name"]}"'
    )
    if eps:
        return eps[0]

    return aiplatform.MatchingEngineIndexEndpoint.create(
        display_name=cfg["endpoint_display_name"],
        public_endpoint_enabled=True
    )

def ensure_deployed(index, endpoint):
    for d in endpoint.deployed_indexes:
        if d.index == index.resource_name:
            print(f"    [Skip] Index already deployed. Deployed Index ID: {d.id}", flush=True)
            return d.id
    
    deployed_id = f"dep_{int(time.time())}"
    print(f"    [Deploy] Starting deployment... (This takes 20~40 minutes. Do NOT exit.)", flush=True)
    print(f"    Target Endpoint: {endpoint.display_name}", flush=True)
    
    endpoint.deploy_index(
        index=index,
        deployed_index_id=deployed_id,
        min_replica_count=1,
        max_replica_count=1
    )
    endpoint = aiplatform.MatchingEngineIndexEndpoint(endpoint.resource_name)
    return endpoint.deployed_indexes[0].id

def chunks_index_by_id():
    m = {}
    for rec in iter_jsonl(CHUNKS_FILE):
        m[rec["id"]] = rec
    return m

def embeddings_index_by_id():
    m = {}
    for rec in iter_jsonl(EMB_FILE):
        m[rec["id"]] = rec["embedding"]
    return m

def smoke_test_vector_search(endpoint, deployed_index_id, emb_map):
    """
    간단한 벡터 검색 테스트 (Top 1)
    """
    try:
        if not emb_map:
            print("    [SmokeTest] No embeddings to test.", flush=True)
            return

        # 첫 번째 임베딩 하나 꺼내서 검색 시도
        test_id = list(emb_map.keys())[0]
        test_emb = emb_map[test_id]
        print(f"\n[SmokeTest] Testing Vector Search with datapoint_id='{test_id}'...", flush=True)
        
        response = endpoint.find_neighbors(
            deployed_index_id=deployed_index_id,
            queries=[test_emb],
            num_neighbors=1
        )
        
        if response:
            print(f"    -> [OK] Search response received: {len(response)} results.", flush=True)
            for res in response:
                print(f"       Top match: {res}", flush=True)
        else:
            print("    -> [WARNING] Empty search response.", flush=True)

    except Exception as e:
        print(f"    -> [FAIL] Smoke test failed: {e}", flush=True)


def main():
    print(f"--- [Step05] Publish Started ---", flush=True)
    print(f"[Config] PUBLISH_MODE = {PUBLISH_MODE}", flush=True)
    
    vec_cfg = load_json(CFG_VEC)
    pol_cfg = load_json(CFG_POL)
    evi = load_json(EVI_FILE) if os.path.exists(EVI_FILE) else {}

    # ---- GCP init ----
    aiplatform.init(project=vec_cfg["project_id"], location=vec_cfg["location"])
    fs = firestore.Client(project=vec_cfg["project_id"])

    col_docs = pol_cfg["firestore"]["collection_docs"]
    col_chunks = pol_cfg["firestore"]["collection_chunks"]
    col_concepts = pol_cfg["firestore"]["collection_concepts"]

    # ---- Vector infra ----
    index = None
    endpoint = None
    deployed_index_id = None

    if PUBLISH_MODE == "both":
        print(f"\n[1] Checking Vector Index ({vec_cfg['index_display_name']})...", flush=True)
        index = get_or_create_index(vec_cfg)
        print(f"    -> Using Index: {index.display_name} ({index.resource_name})", flush=True)

        print(f"\n[2] Checking Endpoint ({vec_cfg['endpoint_display_name']})...", flush=True)
        endpoint = get_or_create_endpoint(vec_cfg)
        print(f"    -> Using Endpoint: {endpoint.display_name} ({endpoint.resource_name})", flush=True)

        print(f"\n[3] Ensuring Index is Deployed to Endpoint...", flush=True)
        deployed_index_id = ensure_deployed(index, endpoint)
        print(f"    -> Deployment Ready. Deployed Index ID: {deployed_index_id}", flush=True)
    else:
        print(f"\n[Skipped] Vector Search steps skipped due to PUBLISH_MODE='{PUBLISH_MODE}'", flush=True)

    # ---- Load local artifacts ----
    print(f"\n[4] Loading local data...", flush=True)
    chunk_map = chunks_index_by_id()
    emb_map = embeddings_index_by_id()
    print(f"    -> Chunks loaded: {len(chunk_map)}", flush=True)
    print(f"    -> Embeddings loaded: {len(emb_map)}", flush=True)
    
    intersect = set(chunk_map.keys()) & set(emb_map.keys())
    print(f"    -> Valid items to process: {len(intersect)}", flush=True)

    # ---- Batch settings ----
    vec_batch = 100  # 좀 더 안정적으로 100 정도 권장
    fs_batch_limit = 400
    vec_datapoints = []
    fs_batch = fs.batch()
    fs_count = 0
    total_fs_commits = 0

    concept_cache = set()
    doc_acc = {}

    pbar_disable = not sys.stdout.isatty()
    
    # 실패 카운트 (Vector Upsert)
    vec_fail_count = 0

    for chunk_id in tqdm(intersect, desc="Publishing", disable=pbar_disable):
        chunk = chunk_map[chunk_id]
        
        # ========== (1) Vector Search upsert 준비 ==========
        md = chunk.get("metadata", {})
        parent_doc_id = chunk.get("parent_doc_id", "unknown")
        
        if PUBLISH_MODE == "both":
            # high-level SDK 사용: namespace, allow_list 필드 주의
            restricts = [
                me.Namespace(name="fileId", allow_tokens=[parent_doc_id]),
                me.Namespace(name="securityLevel", allow_tokens=[md.get("securityLevel", "medium")]),
                me.Namespace(name="department", allow_tokens=[md.get("department", "unknown")]),
                me.Namespace(name="docStatus", allow_tokens=["approved"])
            ]
            
            # create IndexDatapoint using high-level helper
            dp = me.IndexDatapoint(
                datapoint_id=chunk_id,
                feature_vector=emb_map[chunk_id],
                restricts=restricts
            )
            vec_datapoints.append(dp)

        # ========== (2) Firestore: chunk 저장 ==========
        ev = evi.get(chunk_id, {})
        chunk_doc = {
            "chunk_id": chunk_id,
            "parent_doc_id": parent_doc_id,
            "chunk_index": chunk.get("chunk_index", 0),
            "content": chunk.get("content", ""),
            "page": md.get("page", ev.get("page", 1)),
            "tags": md.get("tags", []),
            "securityLevel": md.get("securityLevel", "medium"),
            "department": md.get("department", "unknown"),
            "source_uri": md.get("source_uri", ""),
            "snippet": ev.get("snippet", ""),
            "updatedAt": firestore.SERVER_TIMESTAMP
        }
        fs_batch.set(fs.collection(col_chunks).document(chunk_id), chunk_doc)
        fs_count += 1

        # ========== (3) Firestore: concept(=tags) upsert ==========
        for t in md.get("tags", []):
            concept_id = pol_cfg["concept_strategy"]["concept_id_prefix"] + t
            if concept_id in concept_cache:
                continue
            concept_cache.add(concept_id)
            concept_doc = {
                "id": concept_id,
                "label": t,
                "createdAt": firestore.SERVER_TIMESTAMP
            }
            fs_batch.set(fs.collection(col_concepts).document(concept_id), concept_doc, merge=True)
            fs_count += 1

        # ========== (4) Firestore: doc(DocRecord) 누적 ==========
        if parent_doc_id not in doc_acc:
            doc_acc[parent_doc_id] = {
                "id": parent_doc_id,
                "name": md.get("title", "unknown.pdf"),
                "driveUrl": pol_cfg["docrecord_defaults"]["driveUrl"],
                "folderPath": "",
                "actualPath": pol_cfg["docrecord_defaults"]["actualPath"],
                "tags": md.get("tags", []),
                "period": "",
                "owner": pol_cfg["docrecord_defaults"]["owner"],
                "updatedAt": int(time.time() * 1000),
                "sizeKB": 0,
                "ext": os.path.splitext(md.get("title", "unknown.pdf"))[1].lstrip("."),
                "security": md.get("securityLevel", pol_cfg["docrecord_defaults"]["security"]),
                "aiSummary3": pol_cfg["docrecord_defaults"]["aiSummary3"],
                "textExcerpt": (chunk.get("content", "")[:200] if chunk.get("content") else ""),
                "conceptIds": [pol_cfg["concept_strategy"]["concept_id_prefix"] + t for t in md.get("tags", [])],
                "status": pol_cfg["docrecord_defaults"]["status"],
                "relatedFolderPaths": pol_cfg["docrecord_defaults"]["relatedFolderPaths"]
            }
        else:
            s = set(doc_acc[parent_doc_id]["tags"])
            for t in md.get("tags", []):
                if t not in s:
                    doc_acc[parent_doc_id]["tags"].append(t)
                    doc_acc[parent_doc_id]["conceptIds"].append(pol_cfg["concept_strategy"]["concept_id_prefix"] + t)

        # ---- Firestore batch commit ----
        if fs_count >= fs_batch_limit:
            fs_batch.commit()
            total_fs_commits += 1
            fs_batch = fs.batch()
            fs_count = 0

        # ---- Vector batch upsert ----
        if PUBLISH_MODE == "both" and len(vec_datapoints) >= vec_batch:
            try:
                endpoint.upsert_datapoints(
                    deployed_index_id=deployed_index_id,
                    datapoints=vec_datapoints
                )
            except Exception as e:
                print(f"    [Error] Vector upsert failed for batch of {len(vec_datapoints)}: {e}", flush=True)
                vec_fail_count += len(vec_datapoints)
            
            vec_datapoints = []
            # time.sleep(0.05) # high-level SDK handles some retries, but sleep is safe

    # flush remaining
    if fs_count > 0:
        fs_batch.commit()
        total_fs_commits += 1

    if PUBLISH_MODE == "both" and vec_datapoints:
        try:
            endpoint.upsert_datapoints(deployed_index_id=deployed_index_id, datapoints=vec_datapoints)
        except Exception as e:
            print(f"    [Error] Final vector upsert failed: {e}", flush=True)
            vec_fail_count += len(vec_datapoints)

    print(f"\n[Firestore] Chunks processing done. Total commits: {total_fs_commits}", flush=True)
    if PUBLISH_MODE == "both":
        print(f"[Vector] Upsert finished. Failed datapoints: {vec_fail_count}", flush=True)

    # finally: docs write (DocRecord)
    print(f"[Firestore] Writing DocRecords ({len(doc_acc)} docs)...", flush=True)
    batch = fs.batch()
    count = 0
    docs_commits = 0
    for doc_id, docrec in doc_acc.items():
        batch.set(fs.collection(col_docs).document(doc_id), docrec, merge=True)
        count += 1
        if count >= 400:
            batch.commit()
            docs_commits += 1
            batch = fs.batch()
            count = 0
    if count > 0:
        batch.commit()
        docs_commits += 1
    
    print(f"    -> DocRecords committed in {docs_commits} batches.", flush=True)

    # Sanity Check
    print(f"\n[Sanity Check] Verifying Firestore Write...", flush=True)
    try:
        ping_ref = fs.collection("zz_health").document("ping")
        ping_ref.set({"status": "WRITE_OK", "ts": firestore.SERVER_TIMESTAMP})
        print(f"    -> [OK] Successfully wrote to collection 'zz_health/ping'", flush=True)
        
        # Check first chunk
        sample_chunk_ref = fs.collection(col_chunks).limit(1).get()
        if list(sample_chunk_ref):
            print(f"    -> [OK] Found data in collection '{col_chunks}'", flush=True)
        else:
            print(f"    -> [WARNING] Collection '{col_chunks}' IS EMPTY!", flush=True)

    except Exception as e:
        print(f"    -> [FAIL] Sanity check failed: {e}", flush=True)

    # (Optional) Smoke Test for Vector Search
    if PUBLISH_MODE == "both" and vec_fail_count == 0:
        smoke_test_vector_search(endpoint, deployed_index_id, emb_map)

    print("[SUCCESS] Step05 publish finished.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRITICAL ERROR: {e}")
