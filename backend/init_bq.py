import argparse
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField
from google.api_core.exceptions import NotFound
from app.core.config import settings
import os

# Setup environment (local override)
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"

# BigQuery Settings
DATASET_ID = "omnihub_ai_b_dataset"
LOGS_TABLE = "audit_logs_raw_changelog"
FILES_TABLE = "files_raw_changelog"
LOCATION = "asia-northeast3"

def init_bq():
    print(f"🚀 Initializing BigQuery for Project: {settings.PROJECT_ID}")
    
    client = bigquery.Client(project=settings.PROJECT_ID)
    
    # 1. Create Dataset
    dataset_ref = client.dataset(DATASET_ID)
    try:
        client.get_dataset(dataset_ref)
        print(f"✅ Dataset '{DATASET_ID}' already exists.")
    except NotFound:
        print(f"⚠️ Dataset '{DATASET_ID}' not found. Creating...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = LOCATION
        dataset = client.create_dataset(dataset, timeout=30)
        print(f"✅ Created dataset '{DATASET_ID}'.")

    # 2. Create Logs Table
    logs_table_ref = dataset_ref.table(LOGS_TABLE)
    try:
        client.get_table(logs_table_ref)
        print(f"✅ Table '{LOGS_TABLE}' already exists.")
    except NotFound:
        print(f"⚠️ Table '{LOGS_TABLE}' not found. Creating...")
        schema = [
            SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            SchemaField("document_id", "STRING", mode="REQUIRED"),
            SchemaField("operation", "STRING", mode="REQUIRED"),
            SchemaField("data", "STRING", mode="REQUIRED"), # JSON String
        ]
        table = bigquery.Table(logs_table_ref, schema=schema)
        table = client.create_table(table)
        print(f"✅ Created table '{LOGS_TABLE}'.")

    # 3. Create Files Table
    files_table_ref = dataset_ref.table(FILES_TABLE)
    try:
        client.get_table(files_table_ref)
        print(f"✅ Table '{FILES_TABLE}' already exists.")
    except NotFound:
        print(f"⚠️ Table '{FILES_TABLE}' not found. Creating...")
        schema = [
            SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            SchemaField("document_id", "STRING", mode="REQUIRED"),
            SchemaField("operation", "STRING", mode="REQUIRED"),
            SchemaField("data", "STRING", mode="REQUIRED"), # JSON String
        ]
        table = bigquery.Table(files_table_ref, schema=schema)
        table = client.create_table(table)
        print(f"✅ Created table '{FILES_TABLE}'.")

    print("\n🎉 BigQuery Initialization Complete!")

if __name__ == "__main__":
    init_bq()
