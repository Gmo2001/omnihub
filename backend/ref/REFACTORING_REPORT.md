# Refactoring Report

## 1. 개요
Cloud Run 적합성 확보 및 유지보수성을 위해 OmniHub Backend의 폴더 구조를 재설계하고, 레거시 코드를 정리했습니다.

## 2. 주요 변경 사항

### (1) 폴더 구조 평탄화 (Flattening)
- **SSOT 원칙 적용**:
  - `app/rag/`: 모든 RAG 파이프라인 로직을 이곳으로 통합하였습니다. (기존 `ai_a` 등 제거)
  - `app/commons/`: 공용 스키마 및 상수를 한곳에서 관리합니다.
  - `app/routers/`: FastAPI 라우터를 최상위 `routers` 패키지에 평탄하게 배치했습니다.

### (2) 인증 시스템 개선 (Auth Strategy)
- **ADC (Application Default Credentials) 지원**: 
  - `app/core/gcp_clients.py`를 전면 리팩터링하여, 명시적인 키 파일(`service_account.json`)이 없어도 Cloud Run의 ADC를 통해 인증되도록 변경했습니다.
  - `config.py`의 `GOOGLE_APPLICATION_CREDENTIALS` 설정을 `Optional`로 변경했습니다.

### (3) Import 부작용 제거 (Safe Import)
- **전역 클라이언트 제거**:
  - 기존에 모듈 로딩 시점에 즉시 실행되던 `firestore.client()`, `firebase_admin.initialize_app()` 등을 제거하고, `get_firestore_client()` 팩토리 함수(Lazy Init)로 변경했습니다.
  - 이로 인해 로컬 테스트 및 CI/CD 빌드 시 인증 키가 없어도 앱이 크래시되지 않습니다.

### (4) 레거시 격리
- 구형 코드 (`app/services/ai_a/`, `ai_b/`) 및 미사용 스크립트는 `_archive/` 디렉토리로 이동시켰습니다.
- `.dockerignore`에 `_archive/`를 추가하여 배포 이미지 크기를 최적화했습니다.

## 3. 배포 및 검증 과정 수정 사항 (Deployment Fixes)

### (1) GCP Client 호환성 복구 (`app/core/gcp_clients.py`)
- Lazy Init 적용 과정에서 일부 코드의 `db` 전역 객체 의존성이 확인되었습니다.
- 하위 호환성을 위해 `db = firestore.client()` 초기화 로직을 복구하였으며, Cloud Run 배포 시 `ImportError`를 방지했습니다.

### (2) RAG 모듈 Import 경로 수정 (`app/rag/retriever.py`)
- `FirestoreRepo` 클래스가 `app/rag/`로 이동했음에도 `retriever.py`에서 구형 경로(`app.services.firestore_repo`)를 참조하던 문제를 수정했습니다.
- 수정 경로: `from app.rag.firestore_repo import FirestoreRepo`

## 4. 남아있는 과제 (TODO)
- **패키지 의존성**: 로컬 환경에 `pypdf` 등 일부 패키지가 누락되어 있을 수 있습니다. `pip install -r requirements.txt` 실행이 필요합니다.
- **테스트**: 자동화된 단위 테스트(Unittest) 커버리지를 늘릴 필요가 있습니다.
