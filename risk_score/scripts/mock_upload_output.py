from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from google.cloud import storage
from dotenv import load_dotenv

load_dotenv()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise KeyError("Missing required env: GCP_PROJECT_ID (or GOOGLE_CLOUD_PROJECT)")

    bucket_name = os.environ.get("GCS_BUCKET", "aib-riskscore")
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    trace_id = f"trace_{uuid4().hex}"
    user_id = os.environ.get("TEST_USER_ID", "user_demo")

    payload = {
        "traceId": trace_id,
        "userId": user_id,
        "eventType": os.environ.get("TEST_EVENT_TYPE", "MASS_DOWNLOAD"),
        "reconError": float(os.environ.get("TEST_RECON_ERROR", "0.12")),
        "metadata": {
            "userDownloads5m": int(os.environ.get("TEST_USER_DOWNLOADS_5M", "10")),
            "zPos": float(os.environ.get("TEST_Z_POS", "1.0")),
        },
        "createdAt": utc_stamp(),
    }

    name = f"outputs/{trace_id}.json"
    blob = bucket.blob(name)
    blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")
    print(f"Uploaded: gs://{bucket_name}/{name}")


if __name__ == "__main__":
    main()
