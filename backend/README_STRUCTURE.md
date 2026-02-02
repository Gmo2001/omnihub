# Backend Structure

This repository follows a unified, flat structure optimized for **Cloud Run** and maintainability.

## Directory Layout (SSOT)

```text
backend/app/
├── main.py                  # Application Entry Point (FastAPI)
├── common/                  # Shared Resources (Schemas, Enums) - Single Source of Truth
├── core/                    # Core Configuration (Env, Logging, GCP Clients)
├── routers/                 # API Controllers (Flattened, no deeper nesting)
│   ├── auth.py
│   ├── ingest.py            # Drive Ingestion & Pipeline Trigger
│   ├── rag_search.py        # RAG Search API
│   └── ...
├── rag/                     # RAG Pipeline Logic (Moved from services/rag)
│   ├── orchestrator.py      # Pipeline Manager
│   ├── runner.py            # Cloud Run Job Entry Point
│   ├── retriever.py         # Vector Search Logic
│   └── steps/               # Pipeline Steps (Modularized)
│       ├── run_docai_extract.py
│       ├── build_profile.py
│       └── ...
├── services/                # Domain-Specific Services (Non-RAG)
│   ├── drive_service.py     # Google Drive Integration
│   ├── ingestion_service.py # Helper logic for ingestion
│   └── sync_service.py      # Folder Sync Logic
└── rules/                   # Business Rules (JSON/YAML)

backend/_archive/            # Deprecated/Legacy Code (Do Not Import)
└── legacy_20260202/         # Backup of old 'ai_a', 'ai_b' structures
```

## Execution Guide

### 1. Local Development
```bash
# Run API Server (Hot Reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test RAG Pipeline (Single Doc)
python backend/scripts/test_rag_pipeline.py <DOC_ID>
```

### 2. Cloud Run (Production)

Refer to `DEPLOY_CLOUDRUN.md` for full deployment details.

- **Service (API)**: `CMD ["uvicorn", "app.main:app", ...]`
- **Job (Pipeline)**: `CMD ["python", "-m", "app.rag.runner", ...]`

## Key Modules
- **`app.rag`**: The core RAG engine.
- **`app.routers`**: All HTTP endpoints.
- **`app.common`**: Shared types used by both API and RAG.
