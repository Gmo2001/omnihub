# 1. 파이썬 3.11 슬림 버전 이미지 사용 (가볍고 빠름)
FROM python:3.11-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 필요한 도구 설치 (컴파일러 관련 에러 방지용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스코드 전체 복사 (backend 폴더 내용이 /app으로 들어감)
COPY . .

# 6. 환경 변수 설정 (중요: app 패키지를 인식하게 함)
ENV PYTHONPATH=/app

# 7. 포트 설정 (Cloud Run은 기본적으로 8080을 권장)
EXPOSE 8080

# 8. 서버 실행 명령어 (Uvicorn 이용)
# 0.0.0.0으로 열어야 외부 접속이 가능합니다.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}