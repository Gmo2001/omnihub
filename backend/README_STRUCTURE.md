# Backend Structure (Refactored)

This repository has been refactored to a unified `app` package structure.

## Directory Layout

```text
backend/
├── app/
│   ├── main.py                  # Entry Point (FastAPI)
│   ├── common/                  # Shared Utilities, Enums, Schemas (Unified)
│   ├── core/                    # Config, Logging
│   ├── routers/                 # API Controllers (Flattened)
│   │   ├── ingest.py            # Drive Ingestion
│   │   ├── rag_search.py        # RAG Search API (Moved from rag/app)
│   │   └── ...
│   ├── services/
│   │   ├── rag/                 # RAG Pipeline & Services
│   │   │   ├── orchestrator.py  # Pipeline Manager
│   │   │   ├── steps/           # Individual Pipeline Steps
│   │   │   ├── retriever.py
│   │   │   ├── generator.py
│   │   │   └── ...
│   │   ├── ingestion_service.py # Helper for Ingestion
│   │   └── legacy/              # Deprecated code (Old ai_a structure)
│   └── rules/                   # Business Rules (Unified)
│       └── policy_rules.json
├── scripts/
│   ├── dev/                     # Development/Utility Scripts
│   └── ...
└── ...
```

## Key Changes
- **No more nested `rag/app`**: All RAG logic is now under `app/services/rag`.
- **Unified Schemas**: `app/common/schemas.py` is the single source of truth.
- **Unified Routers**: All API endpoints are in `app/routers`.
- **Legacy Isolation**: Old code moved to `app/services/legacy`.
