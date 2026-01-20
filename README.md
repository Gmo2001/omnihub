# OmniHub Backend

OmniHub의 백엔드 시스템은 **Google Drive**와 **Firestore**를 기반으로 파일 동기화, 로그 추적, AI 분석(AI-B) 데이터를 제공하는 핵심 모듈입니다.
최근 업데이트(v1.1)를 통해 **실제 DB 기반 로깅**과 **Google OAuth 2.0 인증**이 통합되었습니다.

---

## 🚀 주요 업데이트 내역 (v1.1)

### 1. AI-B 이상 징후 탐지용 로그 시스템 구축
AI가 분석할 수 있는 고품질의 학습 데이터를 생성하기 위해 로깅 시스템을 고도화했습니다.

*   **Real-time Snapshot (메타데이터 스냅샷)**: 로그 발생 시점의 사용자/파일 부서 정보를 박제하여 저장.
*   **TTL (Time-To-Live)**: 생성일로부터 1년 후 로그 자동 삭제.
*   **Security Context**: IP 주소 및 User Agent 수집.

### 2. Google OAuth 2.0 인증 시스템 도입
데모용 계정을 제거하고, 실제 구글 계정과 연동되는 보안 시스템을 구축했습니다.
*   **Scope (권한)**: `openid`, `email`, `profile`, `drive.readonly` (파일 목록 조회용)

---

## ⚠️ 현재 제약 사항 (Current Limitations)

개발 초기 단계로 테스트 목적의 제약 사항이 존재합니다. 팀원분들은 아래 내용을 필독해주세요.

### 1. 테스트용 더미 데이터 사용 (Dummy Data)
*   **상황**: 현재 구글 드라이브의 실제 파일 목록을 Firestore로 가져오는 **"실시간 동기화(Sync)" 기능은 구현 예정**입니다.
*   **임시 조치**: AI-B 로그 생성 테스트를 위해 `init_db.py`로 생성한 **더미 파일(`test-file-001`)**을 대상으로만 파일 조회 및 로그 기록이 가능합니다.

### 2. 테스트 사용자 제한 (Test Users Only)
*   **상황**: Google OAuth 앱 상태가 **'테스트(Testing)'** 모드입니다. (민감한 권한 사용을 위한 구글 심사 전 단계)
*   **제약**: Google Cloud Console에 **'테스트 사용자'로 등록된 이메일 계정만 로그인 가능**합니다.
*   **조치**: 팀원들은 관리자에게 Gmail 주소를 전달하여 등록 요청을 해야 합니다.

---

## 🗺️ 향후 로드맵 (Roadmap)

다음 단계로 AI-B 분석 역량 강화와 시스템 완성을 위한 작업들이 예정되어 있습니다.

### 1. Google Drive 완전 연동 (Real Sync)
*   Webhooks(Push Notification)을 활용하여 구글 드라이브에 파일이 생성/수정될 때마다 Firestore 메타데이터를 실시간 동기화합니다.
*   더미 데이터 없이 실제 드라이브 파일을 조회하고 로그를 남길 수 있게 됩니다.

### 2. BigQuery 데이터 파이프라인 구축 (For AI-B)
AI-B 팀이 대규모 로그 데이터를 SQL로 자유롭게 분석하고 모델을 학습시킬 수 있도록 데이터 파이프라인을 구축합니다.
*   **Application Logs**: Firebase Extension(Stream Firestore to BigQuery)을 사용하여 `logs` 컬렉션 데이터를 실시간 적재.
*   **System Logs**: Cloud Logging의 **로그 라우터(Log Router)** 기능을 사용하여 서버 시스템 로그(Stdout/Stderr)를 BigQuery로 자동 전송.

---

## 🛠️ 배포 및 설정 가이드 (Deployment)

본 프로젝트는 **Google Cloud Run**에 배포되어 운영됩니다.

### 1. 사전 준비 (Google Cloud Console)
1.  **OAuth 2.0 클라이언트 ID 생성**:
    *   웹 애플리케이션으로 생성.
    *   **승인된 리디렉션 URI**: `https://[Cloud-Run-URL]/auth/callback` (배포 주소)
2.  **테스트 사용자 추가**:
    *   [OAuth 동의 화면] > [테스트 사용자 (Test Users)] 메뉴에서 팀원들의 Gmail 주소를 모두 등록해야 합니다.

### 2. Cloud Run 배포 (CLI)
다음 명령어로 소스코드와 환경변수 설정을 한 번에 배포할 수 있습니다.

### 3. 테스트 확인 
test_login.html 파일을 웹 브라우저에 열고 확인가능

```powershell
# backend 폴더에서 실행
gcloud run deploy omnihub-backend `
  --source . `
  --region asia-northeast3 `
  --allow-unauthenticated `
  --set-env-vars "PROJECT_ID=jnu-rise-edu-150" `
  --set-env-vars "GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/service_account.json" `
  --set-env-vars "GOOGLE_CLIENT_ID=[발급받은_ID]" `
  --set-env-vars "GOOGLE_CLIENT_SECRET=[발급받은_SECRET]" `
  --set-env-vars "SECRET_KEY=[생성한_랜덤_키]" `
  --set-env-vars "ALGORITHM=HS256"
```

### 3. Cloud Run 콘솔 설정 (필수)
배포 후 콘솔에서 **볼륨 마운트(Volume Mount)**를 반드시 확인/설정해야 합니다.
*   **볼륨 추가**: Secret Manager의 `service_account_json` 선택
*   **마운트 경로**: `/app/secrets` (파일명 `service_account.json`)

---

## 🚨 트러블슈팅 (Troubleshooting)

배포 중 자주 발생하는 오류와 해결 방법입니다.

### Q1. 500 Internal Server Error (Login 시)
*   **원인**: `SessionMiddleware` 누락 또는 `SECRET_KEY` 미설정.
*   **해결**: `main.py`에 미들웨어가 있는지, 환경변수에 키가 잘 들어갔는지 확인하세요.

### Q2. 400 redirect_uri_mismatch
*   **원인**: 구글 콘솔에 등록된 주소와 실제 접근 주소가 다름.
*   **해결**: 에러 화면에 뜬 URL(예: `https://...run.app/auth/callback`)을 그대로 복사해서 구글 콘솔 **[승인된 리디렉션 URI]**에 추가하세요.

### Q3. 403 access_denied (Test User Error)
*   **원인**: "앱이 아직 확인되지 않았습니다" 메시지가 뜨거나 권한 오류 발생.
*   **해결**: Google Cloud Console > [OAuth 동의 화면] > **[테스트 사용자]**에 로그인하려는 계정이 등록되어 있는지 확인하세요.

### Q4. 405 Method Not Allowed (CORS Error)
*   **원인**: 브라우저(프론트엔드)와 서버(백엔드)의 주소가 달라서 보안 정책상 차단됨.
*   **해결**: `main.py`에 `CORSMiddleware`를 추가하여 모든 출처(`*`) 허용 설정을 적용해야 합니다.


---

## 📚 데이터베이스 스키마 (`logs`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `timestamp` | Date | 발생 시각 |
| `user_id` | String | **[Real]** 로그인한 사용자 이메일 |
| `action_type` | String | VIEW / DOWNLOAD |
| `file_department_id` | String | **[Snapshot]** 당시 파일 부서 |
| `ip_address` | String | 접속 IP |
