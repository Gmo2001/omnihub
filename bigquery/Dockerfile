# 1. 파이썬 3.10 슬림 버전 사용 (가볍고 빠름)
FROM python:3.10-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. 의존성 파일 복사 및 설치
# (requirements.txt가 없다면 아래 라이브러리들을 직접 설치하도록 구성)
RUN pip install --no-cache-dir \
    google-cloud-bigquery \
    google-cloud-storage \
    pyyaml \
    flask \
    gunicorn

# 5. 소스 코드 및 SQL 폴더 전체 복사
COPY . .

# 6. 서비스 계정 키 환경변수 설정 (나중에 Cloud Run 설정 시 사용 권장)
# 보안상 실제 배포 시에는 키 파일 대신 'Run 서비스 계정' 권한을 쓰는 것이 좋지만, 
# 현재 구조 유지를 위해 파일명을 지정합니다.
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/service-account.json

# 7. Cloud Run은 포트 8080으로 들어오는 HTTP 요청을 기다려야 함
# 이를 위해 Flask를 사용하여 pipeline.py를 실행할 '서버' 역할을 부여함
EXPOSE 8080

# 8. 실행 명령 (Gunicorn 서버로 Flask 앱 실행)
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main_app:app"]