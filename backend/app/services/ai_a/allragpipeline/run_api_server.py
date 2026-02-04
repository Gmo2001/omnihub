import os
import logging
import uuid
import time
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# 로컬 환경 변수 로드
load_dotenv()

# --- Configuration ---
class Config:
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", 8000))
    CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Logger ---
logging.basicConfig(level=Config.LOG_LEVEL)
logger = logging.getLogger("OmnihubAPI")

# --- App Initialization ---
app = FastAPI(
    title="Omnihub RAG API",
    description="Backend API for Omnihub RAG System",
    version="0.1.0"
)

# --- Middleware ---
# Middleware execution order: Last Added = First Executed (Outermost)
# Desired: CORS -> RateLimit -> Auth -> Context(Optional)

# 0. Global Context & Error Handler
# We define it here so it's added first (innermost/close to router? No, wait.)
# If we want CORS to handle 500 from ContextMiddleware, CORS must be OUTERMOST.
# If ContextMiddleware handles 500, it returns Response. CORS must wrap that Response.
# So CORS > ContextMiddleware.
# So ContextMiddleware must be added BEFORE CORS.
# If we add ContextMiddleware FIRST, then CORS LAST.
# Order of addition:
# 1. ContextMiddleware
# 2. Auth
# 3. RateLimit
# 4. CORS

@app.middleware("http")
async def context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(round(process_time, 4))
        return response
        
    except Exception as e:
        logger.error(f"Global Ex: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": str(e),
                "request_id": request_id
            }
        )

# 1. Auth Context Middleware
from routers.auth_context import AuthContextMiddleware
app.add_middleware(AuthContextMiddleware)

# 2. Rate Limit Middleware
from routers.rate_limit_guard import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# 3. CORS (Must be last to wrap everything, handling 401/429 errors from inner layers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
from app.services.ai_a.allragpipeline.routers import graph_api, card_docs_api, rag_api, docs_status_api, tree_api, download_api

# 4. Include Routers
app.include_router(graph_api.router)
app.include_router(card_docs_api.router)
app.include_router(rag_api.router)
app.include_router(docs_status_api.router)
app.include_router(tree_api.router)
app.include_router(download_api.router)

# --- Stub Routers (추후 파일 분리 예정) ---
from fastapi import APIRouter

# Health Check
@app.get("/healthz")
async def health_check():
    return {"status": "ok", "timestamp": time.time()}

# --- Main Entrypoint ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "run_api_server:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=True
    )
