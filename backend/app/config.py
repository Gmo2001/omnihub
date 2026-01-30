import os

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "(default)")

VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
ME_ENDPOINT_NAME = os.environ.get("ME_ENDPOINT_NAME", "")
ME_DEPLOYED_INDEX_ID = os.environ.get("ME_DEPLOYED_INDEX_ID", "")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

COL_DOCS = os.environ.get("COL_DOCS", "omnihub_docs")
COL_CHUNKS = os.environ.get("COL_CHUNKS", "omnihub_chunks")
COL_CONCEPTS = os.environ.get("COL_CONCEPTS", "omnihub_concepts")
COL_HEALTH = os.environ.get("COL_HEALTH", "zz_health")
HEALTH_DOC = os.environ.get("HEALTH_DOC", "ping")
