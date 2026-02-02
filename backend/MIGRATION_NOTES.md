# 리팩터링 및 마이그레이션 노트 (Migration Notes)

## 1. 개요 (Objective)
- **목표**: 복잡하게 중첩된 폴더 구조(`app/services/ai_a/rag...`)를 평탄화하고, RAG 파이프라인의 **SSOT**(Single Source of Truth)를 확립.
- **결과**: `app/rag/`를 메인 RAG 패키지로 승격하고, 구형 코드는 `_archive/`로 격리.

## 2. 경로 변경 매핑 (Path Mapping)

| 기존 경로 (Old Path) | 새로운 경로 (New Path) | 비고 |
|---|---|---|
| `app/services/rag/` | `app/rag/` | **[Core 승격]** RAG 로직의 최상위 폴더 |
| `app/services/ai_a/` | `_archive/legacy_.../legacy/ai_a/` | **[Deleted]** 더 이상 사용 안 함 |
| `app/services/ai_b/` | `_archive/legacy_.../legacy/ai_b/` | **[Deleted]** 더 이상 사용 안 함 |
| `app/services/rag/pipeline_orchestrator.py` | `app/rag/orchestrator.py` | 리네임됨 |
| `app/routers/rag_api.py` | `app/routers/rag_search.py` | 리네임됨 |
| `rag/app/common/` | `app/common/` | 통합됨 (중복 제거) |

## 3. Import 수정 가이드
만약 로컬에 남아있는 스크립트에서 `ModuleNotFoundError`가 발생하면 아래와 같이 수정하세요.

- `from app.services.rag...` -> **`from app.rag...`**
- `from app.services.ai_a...` -> **`from app.rag...`** (대응되는 모듈 찾아서 변경)

## 4. 환경 변수 및 설정
- `requirements.txt`: `google-cloud-aiplatform>=1.38.0` 추가됨.
- `.dockerignore`: `secrets/`, `_archive/` 등이 이미지 빌드에서 제외됨.
