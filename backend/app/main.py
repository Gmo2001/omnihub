from fastapi import FastAPI
from app.routers import files, drive_webhook
from fastapi.responses import PlainTextResponse # 텍스트 응답용

app = FastAPI(title="OmniHub Backend API")

# 라우터 등록
# app.include_router(auth.router)           # 나중에 구현
app.include_router(drive_webhook.router)
# app.include_router(graph.router)          # 나중에 구현
app.include_router(files.router)            # 지금 테스트용


@app.get("/google55f35d8e589dce80.html", response_class=PlainTextResponse)
def google_verification():
    return "google-site-verification: google55f35d8e589dce80.html"

@app.get("/")
def health_check():
    return {"status": "ok", "service": "OmniHub Backend"}
