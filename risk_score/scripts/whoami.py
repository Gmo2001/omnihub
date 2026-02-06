from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def main():
    print("GCP_PROJECT_ID:", os.environ.get("GCP_PROJECT_ID"))
    print("GOOGLE_CLOUD_PROJECT:", os.environ.get("GOOGLE_CLOUD_PROJECT"))
    print("BQ_DATASET:", os.environ.get("BQ_DATASET"))
    print("BQ_TABLE:", os.environ.get("BQ_TABLE"))
    print("GCS_BUCKET:", os.environ.get("GCS_BUCKET"))
    print("FIRESTORE_USERS_COLLECTION:", os.environ.get("FIRESTORE_USERS_COLLECTION"))
    print("FIRESTORE_IDEMPOTENCY_COLLECTION:", os.environ.get("FIRESTORE_IDEMPOTENCY_COLLECTION"))


if __name__ == "__main__":
    main()
