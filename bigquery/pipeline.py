from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import yaml
from google.cloud import bigquery

# 파일 경로 설정
ROOT = Path(__file__).resolve().parent
SQL_DIR = ROOT / "sql"
CFG_PATH = ROOT / "config.yaml"

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

def main():
    # 1. 환경 설정 및 클라이언트 준비
    cfg = load_cfg()
    project_id = cfg["project_id"]
    ds = cfg["datasets"]
    tb = cfg["tables"]
    params = cfg.get("params", {})
    n_days = params.get("n_days", 7)
    location = params.get("location")

    client = bigquery.Client.from_service_account_json(str(ROOT / "service-account.json"))

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

    # 3. 최신 데이터(MAX windowStart)만 CSV로 추출
    vector_table = f"`{project_id}.{ds['features']}.{tb['vector_table']}`"
    
    # 변수 정의 추가 (에러 방지)
    contract_version = "0.1.0"
    now_str = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    trace_id = f"trace_bq_run_{now_str}"
    
    bucket_uri = f"gs://aib-riskscore/inputs/realtime_vector_{now_str}_*.csv"

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

    print(f"[EXPORT] GCS로 데이터 추출 중: {bucket_uri}")
    run_sql(client, export_to_gcs_sql, location=location)
    print(f"[SUCCESS] 모든 작업이 완료되었습니다. (TraceID: {trace_id})")

if __name__ == "__main__":
    main()