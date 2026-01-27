# 🌌 OmniHub Backend (Advanced Edition)

**OmniHub**는 Google Drive의 파일을 실시간으로 감지하고, AI로 심층 분석하며, 모든 활동 데이터를 BigQuery로 적재하여 데이터 기반 의사결정을 지원하는 **엔터프라이즈급 데이터 통합 플랫폼**입니다.

본 프로젝트는 단순한 드라이브 연동을 넘어, **AI-A(분석 모델)** 및 **AI-B(이상징후 탐지)** 팀과의 유기적인 협업을 목표로 4단계에 걸쳐 고도화되었습니다.

---

## � 고도화 여정 (Evolution History)

### **Phase 1: Foundation (기반 구축)**
*   **Google OAuth 2.0 인증**: 보안 토큰 기반의 사용자 인증 체계 구축.
*   **Drive API 연동**: 파일 리스트 조회 및 기본 메타데이터 동기화.
*   **FastAPI 아키텍처**: 비동기 처리에 최적화된 고성능 백엔드 프레임워크 도입.

### **Phase 2: Reliability & Automation (안정성 강화)**
*   **Auto-Watch System**: 사용자가 로그인만 하면, 서버가 자동으로 구글 드라이브 변경 알림(Push Notification)을 구독합니다. (만료 자동 연장 포함)
*   **Incremental Sync**: 전체 파일을 매번 긁어오지 않고, 변경된 파일(`changes`)만 감지하여 DB 부하를 최소화했습니다.
*   **GCS Direct Streaming**: 파일을 서버 메모리에 담아두지 않고, Google Cloud Storage로 직접 스트리밍하여 대용량 파일도 안정적으로 처리합니다.

### **Phase 3: Intelligence (AI 파이프라인)**
*   **Metadata & Content Extraction**: 파일의 소유자 권한, 수정 이력부터 텍스트 내용까지 심층 추출합니다.
*   **AI-A Collaboration Interface**: `analysis_service.py`를 통해 AI 모델(Gemini, DocAI)이 분석한 결과를 구조화된 데이터(`ai_insights`)로 저장합니다.
*   **Processing Status Management**: `pending` -> `processing` -> `completed` 상태 관리로 분석 누락을 방지합니다.

### **Phase 4: Data Engineering (BigQuery 로그 파이프라인)**
*   **Dual Pipeline Architecture**: 목적에 따라 로그 파이프라인을 이원화했습니다.
    1.  **Audit Logs**: 사용자 행동(누가, 언제, 무엇을) -> Firestore Extension -> BigQuery
    2.  **System Logs**: 시스템 이벤트(AI 분석 완료, 에러) -> Log Router -> BigQuery
*   **Cost Optimization**: 시스템 로그는 날짜별 파티션 테이블(`_YYYYMMDD`)로 적재하여 조회 비용을 절감합니다.

---

## 🤝 협업 가이드 (For Developers)

이 프로젝트는 백엔드 개발자뿐만 아니라, 데이터 사이언티스트 및 분석가와의 협업을 고려하여 설계되었습니다.

### 🧠 For **AI-A Developer** (분석 모델링)
*   **담당 영역**: `app/services/ai_a/analysis_service.py`
*   **임무**: 추출된 텍스트(`extracted_text`)를 입력받아 요약, 키워드, 감정 분석 등을 수행하고 결과를 반환합니다.
*   **데이터 흐름**: `Files (Collection)` -> `Content Extraction` -> **[AI Model]** -> `DB Update`

### 📈 For **AI-B Developer** (데이터 분석/이상탐지)
*   **담당 영역**: Google BigQuery (`jnu-rise-edu-150.omnihub_ai_b_dataset`)
*   **임무**: 적재된 로그 데이터를 분석하여 "권한 없는 파일 접근", "대량 다운로드" 등의 이상 징후를 탐지합니다.

---

## 🛠️ 기술 스택 (Tech Stack)

| Category | Technology | Usage |
| :--- | :--- | :--- |
| **Backend** | Python 3.11, FastAPI | Main API Server |
| **Database** | Google Firestore (NoSQL) | Metadata & User Data |
| **Storage** | Google Cloud Storage (GCS) | Raw File Storage |
| **Data Warehouse** | Google BigQuery | Audit & System Logs |
| **Authentication** | Google OAuth 2.0 | Identity Provider |
| **Infrastructure** | Google Cloud Run | Serverless Deployment |

