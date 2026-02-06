from __future__ import annotations

import os
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()


def main():
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise KeyError("Missing required env: GCP_PROJECT_ID (or GOOGLE_CLOUD_PROJECT)")

    dataset_id = os.environ["BQ_DATASET"]
    table_id = os.environ.get("BQ_TABLE", "risk_events")

    client = bigquery.Client(project=project_id)

    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.location = os.environ.get("BQ_LOCATION", "asia-northeast3")

    # dataset create (exists ok)
    client.create_dataset(dataset_ref, exists_ok=True)

    schema = [
        bigquery.SchemaField("ts", "TIMESTAMP"),
        bigquery.SchemaField("traceId", "STRING"),
        bigquery.SchemaField("userId", "STRING"),
        bigquery.SchemaField("eventType", "STRING"),
        bigquery.SchemaField("reconError", "FLOAT"),
        bigquery.SchemaField("eventRisk", "INTEGER"),
        bigquery.SchemaField("riskScore", "INTEGER"),
        bigquery.SchemaField("defconMode", "STRING"),
        bigquery.SchemaField("stateChanged", "BOOLEAN"),
        bigquery.SchemaField("gcsBucket", "STRING"),
        bigquery.SchemaField("gcsObject", "STRING"),
        bigquery.SchemaField("gcsGeneration", "STRING"),
        bigquery.SchemaField("metadata", "STRING"),
    ]

    table_ref = bigquery.Table(f"{project_id}.{dataset_id}.{table_id}", schema=schema)
    client.create_table(table_ref, exists_ok=True)

    print(f"OK: {project_id}.{dataset_id}.{table_id}")


if __name__ == "__main__":
    main()
