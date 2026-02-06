from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    project_id: str
    bucket: str

    fs_users_col: str
    fs_idem_col: str

    bq_dataset: str
    bq_table: str


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        raise KeyError(f"Missing required env: {name}")
    return str(v).strip()


def load_settings() -> Settings:
    # Cloud Run에서는 GOOGLE_CLOUD_PROJECT가 기본으로 잡히는 경우가 많아서 fallback 제공
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id is None or str(project_id).strip() == "":
        raise KeyError("Missing required env: GCP_PROJECT_ID (or GOOGLE_CLOUD_PROJECT)")

    bucket = os.environ.get("GCS_BUCKET", "aib-riskscore")

    # ✅ 기본값을 risk_users_latest로 바꿔서 실수로 users 덮어쓰는 리스크 제거
    fs_users_col = os.environ.get("FIRESTORE_USERS_COLLECTION", "risk_users_latest")
    fs_idem_col = os.environ.get("FIRESTORE_IDEMPOTENCY_COLLECTION", "ingestions")

    bq_dataset = _require_env("BQ_DATASET")
    bq_table = os.environ.get("BQ_TABLE", "risk_events")

    return Settings(
        project_id=str(project_id).strip(),
        bucket=bucket,
        fs_users_col=fs_users_col,
        fs_idem_col=fs_idem_col,
        bq_dataset=bq_dataset,
        bq_table=bq_table,
    )
