# 옴니허브(Omnihub) 백엔드 파이프라인 & API

이 저장소는 옴니허브(Omnihub)의 운영 가능한 RAG (검색 증강 생성) 파이프라인과 API 서버 구현체입니다.
Google Drive의 문서를 동기화하는 시점부터, 전처리를 거쳐 지식 그래프(Knowledge Graph) 및 벡터 인덱스를 구축하고, 최종적으로 API를 통해 RAG 답변과 그래프 데이터를 서빙하는 전체 과정을 다룹니다.

---

## 🏗️ 아키텍처 개요

시스템은 **수집 및 파이프라인 실행**(`bulk_pipeline_runner.py`)과 데이터를 조회하는 **API 서버**(`run_api_server.py`)로 구성됩니다. 모든 데이터 처리는 테넌트(Tenant) 및 프로젝트(Engagement) 단위로 격리되어 보안을 보장합니다.

| 단계 | 구성 요소 | 역할 | 핵심 스크립트 |
| :--- | :--- | :--- | :--- |
| **1. 수집** | **Bulk Sync & Runner** | Drive 동기화 후 파이프라인 대량 실행 | `bulk_pipeline_runner.py` (Main Entry) <br> `sync_drive_to_gcs.py` (Sync) |
| **2. 처리** | **Processing** | 메타 추출, OCR, 청킹, 요약 | `extract_file_meta.py`, `run_docai_extract.py` <br> `split_and_chunk.py`, `summarize_for_card.py` |
| **3. 추출** | **Extraction** (Optimized) | Key Chunk 기반 엔티티/관계 추출 | `extract_entities_relations.py` |
| **4. 지식화** | **Knowledge Graph** | 개념 병합, 엣지 랭킹, 서빙 인덱스 생성 | `build_concepts.py`, `edge_ranker.py` <br> `build_graph_serving_index.py` |
| **5. 인덱싱** | **Indexing** | 벡터/트리 인덱스 구축 및 상태 필터링 | `upsert_vector_index.py` <br> `build_tree_index.py` |
| **6. 서빙** | **Serving API** | RAG 검색, 그래프 탐색, 문서 조회 | `run_api_server.py`, `routers/` |
| **7. 보안** | **Security Guard** | 권한 제어, 테넌트 격리, 상태 관리 | `services/permission_guard.py` <br> `services/doc_workflow_rules.py` |

---

## 🚀 빠른 시작 (Quick Start)

### 1. 필수 조건
* Python 3.10 이상
* Google Cloud 서비스 계정 및 API 활성화 (Firestore, GCS, Vertex AI 등)
* `.env` 설정 (`.env.example` 참고)

### 2. 설치
```bash
python -m venv .venv
. .venv/bin/activate  # Mac/Linux
.\.venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
```

### 3. 파이프라인 실행 (대량 수집 및 처리)
가장 권장되는 실행 방식입니다. Google Drive 동기화부터 RAG 처리까지 한 번에 수행합니다.
```bash
python bulk_pipeline_runner.py --tenant_id "your-tenant" --engagement_id "your-engagement"
```
* **Phase 1 (Sync)**: 지정된 테넌트의 Drive 폴더를 스캔하여 신규 파일을 GCS로 가져옵니다.
* **Phase 2 (Pipeline)**: 처리가 필요한(`active=True`, review `PENDING` 등) 모든 문서에 대해 파이프라인을 실행합니다.

### 4. API 서버 실행
```bash
python run_api_server.py
```
* 서버는 `0.0.0.0:8000`에서 시작됩니다.
* **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **주요 엔드포인트**:
    * `/api/search/rag`: RAG 질문/답변
    * `/api/graph/*`: 지식 그래프 탐색
    * `/api/docs/{id}`: 문서 상세 및 요약 카드
    * `/api/tree`: 폴더/파일 트리 구조 조회

---

## 🔑 주요 변경 및 최적화 기능

### ⚡ 1. Bulk Pipeline 통합
기존에는 동기화(`sync_drive_to_gcs.py`)와 파이프라인 실행을 별도로 했으나, 이제 `bulk_pipeline_runner.py`가 이를 오케스트레이션합니다. 테넌트/인게이지먼트 ID만 주면 전체 동기화 후 미처리 문서만 자동으로 처리합니다.

### ⚡ 2. Entity Extraction 최적화 (Key Chunk Selection)
비용과 속도 절감을 위해 문서 전체가 아닌 **핵심 청크(Key Chunks)**만을 선별하여 엔티티를 추출합니다.
* **Intro**: 상위 3개 청크
* **Outro**: 하위 2개 청크
* **Page Leaders**: 각 페이지의 첫 번째 청크
* 이들을 하나의 Context로 합쳐 LLM을 1회만 호출합니다.

### 🛡️ 3. 보안 및 상태 필터링 (Security & Status)
* **PermissionGuard**: 모든 API 요청에 대해 테넌트 격리를 강제하며, 보안 등급(`security_level`)에 따른 접근을 제어합니다.
* **Status Filtering**:
    * `APPROVED` 문서만 Vector Search 및 Graph Serving Index에 포함됩니다.
    * `PENDING` 문서는 관리자/리뷰어만 조회 가능하며, 일반 사용자의 검색 결과에는 노출되지 않습니다.
    * 상태 변경 시(`PENDING` -> `APPROVED`) 워크플로우 룰에 따라 즉시 검색 가능(`active=True`)해집니다.

### 📂 4. Lazy Loading Tree Index
`build_tree_index.py`는 `tree_index` 컬렉션에 표준화된 폴더 구조를 미리 계산해 둡니다(`children_folders`, `children_docs`). 프론트엔드는 이를 통해 대량의 문서 트리를 지연 로딩(Lazy Loading) 방식으로 빠르게 조회할 수 있습니다.

---

## 🔒 API 권한 및 보안

이 시스템은 **테넌트 격리(Tenant Isolation)**를 최우선으로 합니다. API 요청 시 헤더를 통해 다음 정보를 전달해야 합니다.

| Header | Description |
| :--- | :--- |
| `X-Tenant-Id` | 테넌트 식별자 (필수) |
| `X-Engagement-Id` | 프로젝트 식별자 (필수) |
| `X-User-Id` | 사용자 ID |
| `X-User-Roles` | (Optional) `admin`, `reviewer`, `viewer` |

* **CORS**: 모든 에러 응답(401, 429 등)에도 CORS 헤더가 보장되도록 미들웨어 순서가 최적화되어 있습니다.
* **Scope Check**: 데이터 접근 시 항상 테넌트/인게이지먼트 일치 여부를 검사합니다.

---

## 🏥 Code Health Check
주요 모듈의 임포트 안전성 및 문법 검사를 위해 아래 명령을 실행할 수 있습니다.
```bash
python -c "import sys; sys.path.append('.'); import services.firestore_repo; import services.permission_guard; import routers.docs_status_api; import routers.tree_api; import bulk_pipeline_runner; import build_concepts; import build_graph_serving_index; print('ALL IMPORT SAFETY CHECK PASSED')"
```
