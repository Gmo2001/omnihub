from __future__ import annotations

from cloudevents.http import CloudEvent
import functions_framework
from dotenv import load_dotenv

from config import load_settings
from stores import Stores
from processor import process_gcs_output_json


# 로컬에서는 .env를 읽고, Cloud Run에서는 환경변수로 주입하면 됨
# (Cloud Run에서는 .env 파일이 없어도 상관 없음)
load_dotenv()


@functions_framework.cloud_event
def ingest_autoencoder_output(cloud_event: CloudEvent):
    data = cloud_event.data or {}

    bucket = str(data.get("bucket", "")).strip()
    name = str(data.get("name", "")).strip()

    # Storage 이벤트에는 generation이 있는 경우가 일반적
    generation = data.get("generation", None)
    if generation is not None:
        generation = str(generation)

    # 안전장치: outputs/*.json만 처리
    if not (name.startswith("outputs/") and name.endswith(".json")):
        return ("ignored", 204)

    settings = load_settings()

    stores = Stores(
        project_id=settings.project_id,
        bq_dataset=settings.bq_dataset,
        bq_table=settings.bq_table,
        fs_users_col=settings.fs_users_col,
        fs_idem_col=settings.fs_idem_col,
    )

    result = process_gcs_output_json(
        stores=stores,
        bucket=bucket or settings.bucket,
        name=name,
        generation=generation,
    )

    if result.get("skipped"):
        return ("duplicate", 204)

    return ("ok", 200)
