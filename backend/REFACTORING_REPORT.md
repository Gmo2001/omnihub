# 리팩터링 결과 보고서: 파일 변경 및 구조 개선

이 문서는 저장소 리팩터링 과정에서 수행된 변경 사항과 파일 구조 개선 내역을 정리한 문서입니다. Cloud Run 배포 준비와 유지보수성 향상을 목적으로 합니다.

## 1. 새로 생성된 파일 (New Files)

새로운 구조를 지원하거나 배포/실행 편의를 위해 신규 작성된 파일들입니다.

| 파일 경로 | 역할/기능 | 설명 |
|---|---|---|
| `app/services/rag/runner.py` | **Cloud Run Job 실행기** | HTTP 타임아웃 없이 파이프라인을 비동기로 실행하기 위한 CLI 스크립트입니다. <br>사용법: `python -m app.services.rag.runner` |
| `DEPLOY_CLOUDRUN.md` | **배포 가이드** | Cloud Run Service(API) 및 Jobs(Pipeline) 배포 방법과 환경 변수 설정 등 운영 가이드를 담고 있습니다. |
| `README_STRUCTURE.md` | **폴더 구조 문서** | 리팩터링된 현재 프로젝트의 폴더 트리와 각 디렉토리의 역할을 설명합니다. |
| `.env.example` | **환경 변수 템플릿** | 로컬 및 운영 환경에서 필요한 필수 환경 변수 목록을 통합 정리했습니다. (배포 시 참조) |
| `app/services/legacy/LEGACY.md` | **Legacy 격리 안내** | 구형 코드들이 `app/services/legacy`로 이동되었음을 알리고, 사용 금지를 안내하는 마커 파일입니다. |

---

## 2. 수정된 파일 (Modified Files)

기존에 존재했으나 리팩터링 과정에서 위치가 바뀌거나 내용이 변경된 파일들입니다.

| 파일 경로 | 역할/기능 | 수정된 내용 상세 |
|---|---|---|
| `app/main.py` | **App 메인 진입점** | - **Import 수정:** 중첩되었던 `app.services.ai_a...rag_api` 임포트를 제거하고 `app.routers.rag_search`로 교체했습니다.<br>- **Router 변경:** 통합된 RAG API 라우터를 등록하도록 코드를 수정했습니다. |
| `app/routers/ingest.py` | **Ingest API** | - **경로 업데이트:** `PipelineOrchestrator`와 `DocAIExtractor`를 더 이상 구형 경로(`ai_a`)가 아닌 **새 경로(`app.services.rag...`)**에서 불러오도록 수정했습니다. |
| `scripts/test_rag_pipeline.py` | **테스트 스크립트** | - **테스트 보정:** 파이프라인 테스트 시 호출하는 오케스트레이터 경로를 새 구조(`app.services.rag.orchestrator`)로 업데이트하여 테스트가 깨지지 않게 했습니다. |
| `.dockerignore` | **빌드 제외 설정** | - **보안 강화:** `secrets/`, `.env`, `service_account.json` 등 민감한 파일이 Docker 이미지에 포함되지 않도록 제외 규칙을 추가했습니다. |
| `app/common/enums.py` | **공통 Enum** | - **중복 통합:** 분산되어 있던 Enum 정의들을 하나로 합치고, RAG 파이프라인 최신 버전을 기준으로 단일화했습니다. |
| `app/common/vector_schema.py` | **벡터 스키마** | - **스키마 통합:** 여러 곳에 있던 벡터 스키마 정의를 `app/common`으로 모으고 최신 상태로 갱신했습니다. |

---

## 3. 구조 변경 요약 (Before vs After)

### Before (변경 전)
- **중첩된 앱 패키지**: `backend/app/` 하위에 또다시 `services/ai_a/rag/app/`이 존재하여 Import 충돌 위험이 컸음.
- **로직 분산**: 파이프라인 단계 로직들이 `services/ai_a/` 바로 아래에 흩어져 있어 가독성이 낮음.
- **중복 리소스**: `rules/`와 `schemas`가 여러 위치에 복제되어 있어 관리 어려움.

### After (변경 후)
- **단일 루트 구조**: 모든 코드가 `backend/app/` 아래로 체계적으로 통합됨.
- **서비스 응집성**: RAG 관련 로직은 모두 `app/services/rag/` 하위로 모아 관리.
- **API 플랫화**: 모든 API 컨트롤러(라우터)는 `app/routers/`에 1 depth로 정리 (`rag_search.py` 등).
- **Legacy 격리**: 더 이상 쓰지 않는 코드는 `app/services/legacy/`로 이동시켜 혼란 방지.
