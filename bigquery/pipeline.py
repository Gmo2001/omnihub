from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import yaml
import json
import os
import joblib
import numpy as np
import pandas as pd
from google.cloud import bigquery
from google.cloud import storage

# Autoencoder Inference Deps (Lazy import is handled by top-level import here as container handles deps)
from tensorflow import keras

# 파일 경로 설정
ROOT = Path(__file__).resolve().parent
SQL_DIR = ROOT / "sql"
CFG_PATH = ROOT / "config.yaml"

# Constants
GCS_BUCKET = "aib-riskscore"
MODEL_GCS_PREFIX = "models"
OUTPUT_GCS_PREFIX = "outputs"
TEMP_MODEL_DIR = "/tmp/models"

def load_cfg() -> dict:
    """config.yaml 파일을 읽어옵니다."""
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def read_sql(name: str) -> str:
    """sql 폴더 안의 .sql 파일을 읽어옵니다."""
    return (SQL_DIR / name).read_text(encoding="utf-8")

def apply_vars(sql: str, cfg: dict) -> str:
    """SQL 내의 변수들(${...})을 실제 설정값으로 바꿉니다."""
    project_id = cfg["project_id"]
    ds = cfg["datasets"]
    tb = cfg["tables"]
    params = cfg.get("params", {})
    n_days = int(params.get("n_days", 7))
    action_types = params.get("action_types", {}) or {}
    download_action_type = int(action_types.get("download", params.get("download_action_type", 1)))
    
    return (
        sql.replace("${PROJECT_ID}", project_id)
           .replace("${DS_RAW_AUDIT}", ds["raw_audit"])
           .replace("${DS_RAW_SYSTEM}", ds["raw_system"])
           .replace("${DS_CLEAN}", ds["clean"])
           .replace("${DS_FEATURES}", ds["features"])  
           .replace("${TB_SYSTEM_WILDCARD}", tb["system_stdout_wildcard"])
           .replace("${TB_CLEAN_AUDIT}", tb["clean_audit_view"])
           .replace("${TB_CLEAN_SYSTEM}", tb["clean_system_view"])
           .replace("${TB_USER_5M}", tb["user_5m_view"])
           .replace("${TB_DEPT_STATS}", tb["dept_stats_table"])
           .replace("${TB_VECTOR}", tb["vector_table"])
           .replace("${N_DAYS}", str(n_days))
           .replace("${DOWNLOAD_ACTION_TYPE}", str(download_action_type))
           .replace("${TB_AUDIT_SOURCE}", tb["audit_source"])
    )

def ensure_dataset(client: bigquery.Client, project_id: str, dataset_id: str, location: str | None = None):
    """데이터셋이 없으면 자동으로 생성합니다."""
    ds_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    if location:
        ds_ref.location = location
    client.create_dataset(ds_ref, exists_ok=True)

def run_sql(client: bigquery.Client, sql: str, location: str | None = None):
    """BigQuery에 쿼리를 전송하고 실행합니다."""
    job = client.query(sql, location=location) if location else client.query(sql)
    return job.result()

# --- Autoencoder Helper Functions ---

def download_models_from_gcs():
    """GCS에서 모델 아티팩트를 다운로드합니다."""
    print(f"[MODEL] Downloading models from gs://{GCS_BUCKET}/{MODEL_GCS_PREFIX} to {TEMP_MODEL_DIR}...")
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blobs = bucket.list_blobs(prefix=MODEL_GCS_PREFIX)
    
    if not os.path.exists(TEMP_MODEL_DIR):
        os.makedirs(TEMP_MODEL_DIR)

    downloaded_files = []
    for blob in blobs:
        if blob.name.endswith("/"): continue
        filename = os.path.basename(blob.name)
        local_path = os.path.join(TEMP_MODEL_DIR, filename)
        blob.download_to_filename(local_path)
        downloaded_files.append(local_path)
        print(f" - Downloaded: {filename}")
    
    if not downloaded_files:
        raise FileNotFoundError(f"No model files found in gs://{GCS_BUCKET}/{MODEL_GCS_PREFIX}")
    
    return downloaded_files

def load_inference_artifacts():
    """로컬 /tmp/models 에서 아티팩트 로드"""
    model_path = os.path.join(TEMP_MODEL_DIR, "autoencoder.keras")
    scaler_path = os.path.join(TEMP_MODEL_DIR, "scaler.pkl")
    baseline_path = os.path.join(TEMP_MODEL_DIR, "baseline.json")

    # 모델 파일이 하나라도 없으면 에러 (학습 먼저 수행 필요)
    if not (os.path.exists(model_path) and os.path.exists(scaler_path) and os.path.exists(baseline_path)):
        raise FileNotFoundError("Model artifacts missing in /tmp/models. Please run training first.")

    model = keras.models.load_model(model_path)
    scaler = joblib.load(scaler_path)
    with open(baseline_path, "r") as f:
        baseline = json.load(f)
        
    return model, scaler, baseline

def score_dataframe(model, scaler, baseline, df):
    """
    DataFrame을 입력받아 이상 점수(Risk)를 계산하고 DF에 추가합니다.
    """
    # 1. Feature Selection (Training 시 사용한 컬럼과 동일해야 함)
    feature_cols = ["userDownloads5m", "zPos"]
    
    # Ensure columns exist, fillna with 0 for safety
    X_raw = df[feature_cols].fillna(0).values
    
    # 2. Transform
    X_scaled = scaler.transform(X_raw)
    
    # 3. Predict & Recon Error
    X_pred = model.predict(X_scaled)
    # MSE axis 1
    recon_err = np.mean((X_scaled - X_pred) ** 2, axis=1)
    
    # 4. Z-Score & Anomaly Score
    train_mean = baseline.get("trainMean", baseline.get("train_mean", 0.0))
    train_std = baseline.get("trainStd", baseline.get("train_std", 1.0))
    # Z-score
    z_scores = (recon_err - train_mean) / (train_std + 1e-8)
    
    df["reconError"] = recon_err
    df["anomalyScore"] = z_scores 
    
    # 5. Metadata columns
    df["trainMean"] = train_mean
    df["trainStd"] = train_std
    df["p95Threshold"] = baseline.get("p95Threshold", baseline.get("p95_threshold", 0.0))

    return df

def upload_results_to_gcs_json(df):
    """
    DataFrame의 각 행을 개별 JSON 이벤트 파일로 변환하여 GCS outputs/ 에 업로드.
    (Risk Score Cloud Function 트리거용)
    """
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    
    now_ts = datetime.now(timezone.utc).isoformat()
    
    print(f"[OUTPUT] Uploading {len(df)} events to gs://{GCS_BUCKET}/{OUTPUT_GCS_PREFIX}/ ...")
    
    for idx, row in df.iterrows():
        user_id = str(row.get("userId", "unknown"))
        trace_id = str(row.get("traceId", "no_trace"))
        
        # Risk Score Processor가 기대하는 포맷 + 오토인코더 원본 Flat 포맷 호환
        # 오토인코더 원본 데이터 예시:
        # {
        #   "traceId": "test_anomaly",
        #   "windowStart": "2026-02-02",
        #   "userId": "user2",
        #   "eventType": 1,
        #   "trainMean": 0.644,
        #   "trainStd": 1.49,
        #   "p95Threshold": 1.85,
        #   "reconError": 2.67,
        #   "userDownloads5m": 5,
        #   "zPos": 3
        # }
        
        # 1. 원본 데이터 값 추출 & Rule-based Type 결정
        feat_downloads = float(row.get("userDownloads5m", 0))
        feat_zpos = float(row.get("zPos", 0))
        feat_deny_cnt = float(row.get("denyCount5m", 0))
        feat_deny_ratio = float(row.get("denyRatio5m", 0))
        feat_recon = float(row.get("reconError", 0))
        feat_p95 = float(row.get("p95Threshold", 0))
        
        # Rule Base Logic
        if feat_deny_cnt >= 1 or feat_deny_ratio >= 0.2:
            event_type = "DENY_ACCESS"
        elif feat_downloads >= 5: # 5건 이상이면 대량 (테스트용)
            event_type = "MASS_DOWNLOAD"
        elif feat_p95 > 0 and feat_recon >= feat_p95:
            event_type = "MODEL_ANOMALY"
        else:
            event_type = "NORMAL_ACTIVITY"
        
        payload = {
            "traceId": trace_id,
            "userId": user_id,
            "eventType": event_type,
            "windowStart": str(row.get("windowStart", "")),
            
            # 모델 결과
            "reconError": float(row["reconError"]),
            "anomalyScore": float(row["anomalyScore"]), # 계산된 Z-Score (추가 정보)
            
            # Baseline
            "trainMean": float(row["trainMean"]),
            "trainStd": float(row["trainStd"]),
            "p95Threshold": float(row["p95Threshold"]),
            
            # 원본 피처 (Flat 구조로도 제공)
            "userDownloads5m": feat_downloads,
            "zPos": feat_zpos,
            
            "metadata": {
                "userDownloads5m": feat_downloads,
                "zPos": feat_zpos
            },
            "createdAt": now_ts
        }
        
        # 파일명: outputs/result_{traceId}_{userId}.json
        blob_name = f"{OUTPUT_GCS_PREFIX}/result_{trace_id}_{user_id}.json"
        
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            json.dumps(payload),
            content_type="application/json"
        )
        
    print(f"[SUCCESS] Uploaded {len(df)} JSON files to {OUTPUT_GCS_PREFIX}/")


def main():
    # 1. 환경 설정 및 클라이언트 준비
    cfg = load_cfg()
    project_id = cfg["project_id"]
    ds = cfg["datasets"]
    tb = cfg["tables"]
    params = cfg.get("params", {})
    n_days = params.get("n_days", 7)
    location = params.get("location")

    client = bigquery.Client(project=project_id)

    ensure_dataset(client, project_id, ds["clean"], location=location)
    ensure_dataset(client, project_id, ds["features"], location=location)

    # 2. SQL 순차 실행 (정제 -> 피처 생성)
    steps = [
        "01_clean_audit_view.sql",
        "02_clean_system_view.sql",
        "03_user_5m_view.sql",
        "04_dept_stats_ndays.sql",
        "05_feature_vector_table.sql",
    ]

    for f in steps:
        print(f"[RUNNING] {f} 실행 중...")
        sql = apply_vars(read_sql(f), cfg)
        run_sql(client, sql, location=location)

    # 3. 최신 데이터(MAX windowStart)만 CSV로 추출 (기존 로직 유지 - Job이 inputs 생성)
    vector_table = f"`{project_id}.{ds['features']}.{tb['vector_table']}`"
    
    contract_version = "0.1.0"
    now_str = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    trace_id = f"trace_bq_run_{now_str}"
    
    bucket_uri = f"gs://{GCS_BUCKET}/inputs/realtime_vector_{now_str}_*.csv"

    export_to_gcs_sql = f"""
    EXPORT DATA OPTIONS(
        uri = '{bucket_uri}',
        format = 'CSV',
        overwrite = true,
        header = true
    ) AS
    SELECT
        *,
        '{contract_version}' AS contractVersion,
        '{trace_id}' AS traceId
    FROM {vector_table}
    WHERE windowStart = (SELECT MAX(windowStart) FROM {vector_table})
    ORDER BY userId ASC
    """

    print(f"[EXPORT] GCS로 CSV 입력 데이터 추출 중: {bucket_uri}")
    run_sql(client, export_to_gcs_sql, location=location)
    
    # --- 여기서부터 추가된 로직 (Autoencoder 추론) ---
    print("\n[STEP 2] Running Autoencoder Inference...")
    
    # 4. 추론을 위해 동일한 데이터를 DataFrame으로 로드
    fetch_sql = f"""
    SELECT
        *,
        '{contract_version}' AS contractVersion,
        '{trace_id}' AS traceId
    FROM {vector_table}
    WHERE windowStart = (SELECT MAX(windowStart) FROM {vector_table})
    ORDER BY userId ASC
    """
    
    df = client.query(fetch_sql).to_dataframe()
    if df.empty:
        print("[DONE] No data to process.")
        return

    # [NEW] 데이터 최신성 체크 (15분 이상 지난 데이터면 스킵)
    # windowStart는 이미 UTC로 되어 있음 (BigQuery Timestamp)
    latest_ts = df["windowStart"].max()
    # pandas Timestamp to datetime
    if hasattr(latest_ts, "to_pydatetime"):
        latest_ts = latest_ts.to_pydatetime()
    
    # 시간대 정보 없으면 UTC로 가정
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=timezone.utc)
        
    now_ts = datetime.now(timezone.utc)
    diff = now_ts - latest_ts
    
    print(f"[CHECK] Latest Data: {latest_ts}, Now: {now_ts}, Diff: {diff}")
    
    # 15분(900초) 이상 차이나면 스킵
    if diff.total_seconds() > 900:
        print(f"[SKIP] 최신 데이터가 {diff} 전 데이터입니다. (15분 초과)")
        print("새로운 로그가 들어올 때까지 분석을 건너뜁니다.")
        return

    try:
        # 4-1. 모델 다운로드 & 로딩
        download_models_from_gcs()
        model, scaler, baseline = load_inference_artifacts()
        
        # 4-2. 스코어링
        df_scored = score_dataframe(model, scaler, baseline, df)
        
        # 4-3. 결과 JSON 업로드 (Eventarc 트리거)
        upload_results_to_gcs_json(df_scored)
        
    except Exception as e:
        print(f"[ERROR] Autoencoder process failed: {e}")
        # 중요: CSV Export는 성공했으므로, 여기서 에러를 내되 전체 파이프라인의 실패 여부는 상황에 따라 결정
        # 일단은 실패로 처리하여 로그에서 확인 가능하게 함
        raise e

    print(f"[SUCCESS] 모든 작업이 완료되었습니다. (TraceID: {trace_id})")

if __name__ == "__main__":
    main()