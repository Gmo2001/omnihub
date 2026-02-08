# 1. 파이썬 3.10 슬림 버전 사용
FROM python:3.10-slim

# 2. 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 5. 의존성 파일 복사 및 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 및 SQL 폴더 전체 복사
COPY . .

# 7. Cloud Run은 포트 8080으로 HTTP 요청 수신
# 서비스 계정은 Cloud Run의 기본 서비스 계정(ADC)을 사용
EXPOSE 8080

# Cloud Run Job은 웹 서버가 아니라 스크립트를 한번 실행하고 종료해야 함
# 따라서 functions-framework 대신 파이프라인 스크립트를 직접 실행
CMD ["sh", "-c", "echo 'Current directory contents:' && ls -la && python pipeline.py"]