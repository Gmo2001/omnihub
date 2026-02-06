from __future__ import annotations

import os
import time
from typing import Set

from dotenv import load_dotenv

from config import load_settings
from stores import Stores
from processor import process_gcs_output_json


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def main():
    load_dotenv()

    settings = load_settings()
    stores = Stores(
        project_id=settings.project_id,
        bq_dataset=settings.bq_dataset,
        bq_table=settings.bq_table,
        fs_users_col=settings.fs_users_col,
        fs_idem_col=settings.fs_idem_col,
    )

    poll_seconds = int(os.environ.get("POLL_SECONDS", "5"))
    list_limit = int(os.environ.get("LIST_LIMIT", "200"))
    process_existing = _env_bool("PROCESS_EXISTING_ON_START", False)

    bucket_name = settings.bucket
    bucket = stores.storage.bucket(bucket_name)

    print("=== Local GCS Watcher Started ===")
    print(f"- project: {settings.project_id}")
    print(f"- bucket : {bucket_name}")
    print(f"- prefix : outputs/")
    print(f"- poll   : {poll_seconds}s")
    print(f"- limit  : {list_limit}")
    print(f"- process_existing_on_start: {process_existing}")
    print("================================")

    seen: Set[str] = set()

    while True:
        try:
            blobs = list(
                stores.storage.list_blobs(
                    bucket,
                    prefix="outputs/",
                    max_results=list_limit,
                )
            )

            # 오래된 것부터 처리 (원하면 reverse=True로 바꿔도 됨)
            blobs.sort(key=lambda b: (b.updated or 0), reverse=False)

            # 시작 시점 이전 파일을 스킵하고 싶으면 첫 루프에서 캐시에만 담고 처리 안함
            if not process_existing and not seen:
                for blob in blobs:
                    gen = str(getattr(blob, "generation", "") or "")
                    key = f"{bucket_name}:{blob.name}:{gen}"
                    seen.add(key)
                time.sleep(poll_seconds)
                continue

            for blob in blobs:
                if not blob.name.endswith(".json"):
                    continue

                generation = str(getattr(blob, "generation", "") or "")
                key = f"{bucket_name}:{blob.name}:{generation}"

                if key in seen:
                    continue

                seen.add(key)

                r = process_gcs_output_json(
                    stores=stores,
                    bucket=bucket_name,
                    name=blob.name,
                    generation=generation,
                )

                if r.get("skipped"):
                    print(f"[SKIP] {blob.name} ({generation}) - duplicate")
                elif r.get("ignored"):
                    print(f"[IGNORED] {blob.name} ({generation})")
                else:
                    risk = r.get("risk", {})
                    print(
                        f"[OK] {blob.name} ({generation}) "
                        f"user={r.get('userId')} eventType={r.get('eventType')} "
                        f"eventRisk={risk.get('eventRisk')} riskScore={risk.get('riskScore')} "
                        f"mode={risk.get('defconMode')} changed={risk.get('stateChanged')}"
                    )

        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")

        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
