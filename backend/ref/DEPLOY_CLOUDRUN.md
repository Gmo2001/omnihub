# Deploying to Cloud Run & Cloud Run Jobs

## 1. Prerequisites (GCP Setup)

Ensure you have the following resources created in Google Cloud Platform:
- **Project ID**: Your GCP Project.
- **Service Account**: A dedicated SA with permissions for Firestore, GCS, Vertex AI, and DocAI.
- **Artifact Registry**: A repository to store your Docker images.
- **Secret Manager**: Store sensitive env vars (`SECRET_KEY`, `GOOGLE_CLIENT_SECRET`, etc.) here.

## 2. Build & Push Docker Image

From the `backend/` directory:

```bash
# 1. Set Project
export PROJECT_ID="your-project-id"
export REGION="asia-northeast3" # or us-central1
export REPO_NAME="omnihub-backend"
export IMAGE_TAG="latest"

# 2. Build
gcloud builds submit --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:${IMAGE_TAG}" .
```

## 3. Deploy Service (API Server)

For the FastAPI Web Server (Serving):

```bash
gcloud run deploy omnihub-api \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:${IMAGE_TAG}" \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "PROJECT_ID=${PROJECT_ID},LOG_LEVEL=INFO" \
  --set-secrets "SECRET_KEY=my-secret-key-version:latest" 
  # Add other necessary env vars from .env.example
```

**Entry Point**: Default `CMD` in Dockerfile (`uvicorn app.main:app`).

## 4. Deploy Job (RAG Pipeline)

For background processing (Pipeline Runner):

This runs the RAG pipeline for a specific document without timing out (Cloud Run Service has a 60min limit, Jobs allowed up to 24h).

```bash
gcloud run jobs create omnihub-rag-job \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:${IMAGE_TAG}" \
  --region $REGION \
  --command "python" \
  --args "-m,app.services.rag.runner" \
  --set-env-vars "PROJECT_ID=${PROJECT_ID}" 
  # Add same env vars as service
```

### Triggering the Job manually:

```bash
gcloud run jobs execute omnihub-rag-job \
  --region $REGION \
  --args "--doc_id=YOUR_DOC_ID,--gcs_uri=gs://...,--mime_type=application/pdf"
```

## 5. Environment Variables

Refer to `.env.example` for the full list.
When deploying to Cloud Run, **DO NOT** ship `.env` or `service_account.json`.
Instead:
1. Use **Cloud Secret Manager** for sensitive keys (`SECRET_KEY`, `client_secret`).
2. Attach the Service Account to the Cloud Run instance identity.
3. Pass non-sensitive config via `--set-env-vars`.

## 6. Observability
- **Logs**: Check Cloud Logging. All logs are structured JSON if using the `app.core.logger`.
- **Trace**: `run_id` and `trace_id` are included in log entries.
- **Status**: Pipeline execution status is updated in Firestore (`files/{doc_id}`).
