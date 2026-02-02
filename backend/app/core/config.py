from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "OmniHub"
    PROJECT_ID: str  =""  #외부에서 설정(cloud run)
    SUPER_ADMIN_EMAIL: str = "" # Super Admin Email for initial setup
    
    # Default to service_account.json in the backend root if not set in env
    # GOOGLE_APPLICATION_CREDENTIALS: Optional for Cloud Run (ADC), Required for Local if no gcloud auth
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    
    # OAuth 2.0 (From Google Cloud Console)
    GOOGLE_CLIENT_ID: str = "" 
    GOOGLE_CLIENT_SECRET: str = ""
    SECRET_KEY: str = "" # For signing internal JWT
    ALGORITHM: str = "HS256"

    SECTION_DOCAI: str = "Document AI Settings"
    DOCAI_LOCATION: str = "" # Default location
    DOCAI_PROCESSOR_ID: str = "" # Set via env or .env file

    # RAG - Storage & DB
    FIRESTORE_DATABASE: str = "(default)"
    GCS_BUCKET: str = ""
    GCS_PREFIX: str = "omnihub-data"

    # RAG - Tenant & Scope
    TENANT_ID: str = "default"
    ENGAGEMENT_ID: str = "default"
    
    # RAG - DocAI
    DOC_AI_LOCATION: str = "us"
    DOC_AI_PROCESSOR_ID_PDF: str | None = None
    DOC_AI_PROCESSOR_ID_IMAGE: str | None = None
    CHUNK_SIZE_HINT: int = 1000
    CHUNK_OVERLAP_HINT: int = 200

    # RAG - AI & Embedding
    VERTEX_LOCATION: str = "us-central1"
    VERTEX_MODEL_NAME: str = "gemini-1.5-flash-001"
    VERTEX_EMBED_MODEL: str = "text-embedding-004"
    EMBEDDING_PROVIDER: str = "vertex" # vertex or openai

    # RAG - Vector Search
    VECTOR_INDEX_NAME: str | None = None
    VECTOR_INDEX_ENDPOINT: str | None = None
    VECTOR_DEPLOYED_INDEX_ID: str | None = None
    VECTOR_DIM: int = 768
    VECTOR_UPSERT_BATCH_SIZE: int = 50

    # RAG - Logic Versions & Caps
    PIPELINE_VERSION: str = "v1"
    POLICY_RULE_VERSION: str = "v1"
    CONCEPT_RULES_VERSION: str = "v1"
    EDGE_RANKER_VERSION: str = "v1"
    DOC_INDEX_VERSION: str = "v1"
    
    TOP_CONCEPTS_CAP: int = 50
    PER_DOC_CAP: int = 50

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
