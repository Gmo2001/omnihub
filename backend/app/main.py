from fastapi import FastAPI
from app.routers import (
    files, drive_webhook, auth, admin, ingest, rag_search,
    tree_api, graph_api, card_docs_api, docs_status_api, download_api
)
# from app.services.ai_a.rag.app.api.routers import rag_api # Removed in refactor
from fastapi.responses import PlainTextResponse # 텍스트 응답용

from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(title="OmniHub Backend API")

# 1. CORS 설정 (가장 먼저 추가)
# 로컬 HTML 파일에서 API를 호출하려면 필수입니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 모든 출처 허용 (보안을 위해 나중엔 프론트엔드 도메인만 허용해야 함)
    allow_credentials=True,
    allow_methods=["*"],      # 모든 HTTP 메서드 허용 (GET, POST, OPTIONS 등)
    allow_headers=["*"],      # 모든 헤더 허용 (Authorization 등)
)

from app.routers.auth_context import AuthContextMiddleware

# 2. Authlib을 위한 세션 미들웨어 추가
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# 3. Custom Auth Context Middleware (Headers -> AuthContext)
app.add_middleware(AuthContextMiddleware)

# 4. Rate Limit Middleware (Traffic Control)
from app.routers.rate_limit_guard import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


# 라우터 등록
app.include_router(auth.router)             # 인증 라우터 등록
app.include_router(drive_webhook.router)
app.include_router(admin.router)            # Admin APIS
app.include_router(ingest.router)           # Drive Ingestion
app.include_router(rag_search.router)       # RAG API (Retrieval & Generation)

# RAG UI Routers
app.include_router(tree_api.router)         # Folder Tree
app.include_router(graph_api.router)        # Knowledge Graph
app.include_router(card_docs_api.router)    # Doc Detail & Card
app.include_router(docs_status_api.router)  # Approval Workflow
app.include_router(download_api.router)     # File Download

# app.include_router(graph.router)          # (Legacy or Placeholder)
app.include_router(files.router)            # (Test/Legacy)


#Google 웹사이트 소유권 확인용
@app.get("/google55f35d8e589dce80.html", response_class=PlainTextResponse)
def google_verification():
    return "google-site-verification: google55f35d8e589dce80.html"

#health check
@app.get("/")
def health_check():
    return {"status": "ok", "service": "OmniHub Backend"}

# [Frontend] Serve Static Files
from fastapi.staticfiles import StaticFiles
import os

# Create static dir if not exists
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/console", StaticFiles(directory="static", html=True), name="static")
