from fastapi import FastAPI
from app.routers import files, drive_webhook, auth
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

# 2. Authlib을 위한 세션 미들웨어 추가
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


# 라우터 등록
app.include_router(auth.router)           # 인증 라우터 등록
app.include_router(drive_webhook.router)
# app.include_router(graph.router)          # 나중에 구현
app.include_router(files.router)            # 지금 테스트용


@app.get("/google55f35d8e589dce80.html", response_class=PlainTextResponse)
def google_verification():
    return "google-site-verification: google55f35d8e589dce80.html"

@app.get("/")
def health_check():
    return {"status": "ok", "service": "OmniHub Backend"}
