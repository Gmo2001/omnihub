# 유틸리티 스크립트 (Omnihub Pipeline)

이 디렉토리는 옴니허브(Omnihub) 파이프라인의 테스트, 디버깅 및 유지보수를 위한 스크립트 모음입니다.

## 🧪 테스트 및 검증 도구

### 통합 테스트 (Integration Tests)
* **`final_pipeline_test.py`** (추천)
    * RAG API의 전체 흐름(End-to-End)을 테스트합니다.
    * 인증(Auth), 테넌트 격리(보안), 답변 품질(Gemini 응답)을 종합적으로 검증합니다.
    * 사용법: `python utilly/final_pipeline_test.py`

* **`test_rag_api.py`**
    * RAG 검색 API (`/api/search/rag`)를 직접 호출 테스트합니다.
    * 답변 텍스트, 인용 문서(Citations), 응답 속도(Latency)를 출력합니다.

* **`test_download_api.py`**
    * 보안 다운로드 API (`/api/docs/{id}/download`)를 테스트합니다.
    * 유효한 Signed URL이 발급되는지 확인합니다.

* **`test_workflow.py`**
    * 문서 상태 관리 API (`PATCH /api/docs/{id}/status`)를 테스트합니다.
    * 상태 변경(승인/거절 등)에 따라 검색 노출 여부(Active Flag)가 올바르게 업데이트되는지 검증합니다.

### 단위 및 컴포넌트 테스트 (Unit Tests)
* **`test_security_logic.py`**
    * `services/permission_guard.py`의 보안 로직을 테스트합니다.
    * 해커, 관리자, 일반 사용자 등 다양한 상황을 가정하여 접근 제어 규칙이 작동하는지 확인합니다.

* **`test_retriever_direct.py`**
    * API를 거치지 않고 `services.retriever.Retriever` 클래스를 직접 호출합니다.
    * Vector Search 결과와 필터링 로직을 디버깅할 때 유용합니다.

* **`test_generator_direct.py`**
    * LLM 생성 로직(`services.generator.Generator`)을 Mock 데이터로 테스트합니다.

* **`test_graph.py`**
    * 지식 그래프 쿼리(Node/Edge 조회) 로직을 테스트합니다.

## 🛠️ 디버깅 및 유지보수

* **`reset_card_flags.py`**
    * Firestore 문서의 특정 플래그를 초기화합니다 (예: 카드 재생성을 위해 플래그 리셋).

* **`reset_entities.py`**
    * 추출된 엔티티 데이터를 초기화하여 재추출을 유도합니다.

* **`inspect_folders.py`**
    * 트리가 올바르게 구성되었는지 Firestore의 폴더 구조를 검사합니다.

* **`debug_retriever_raw.py`**
    * Retriever 클래스마저 배제하고, Vertex AI Vector Search에 날것의(Raw) 쿼리를 보냅니다.
    * 임베딩 생성이나 인덱스 자체에 문제가 있는지 확인할 때 사용합니다.

## ⚠️ 참고 사항
대부분의 스크립트는 상위 디렉토리의 `.env` 환경 변수 파일 설정이 필요합니다.
스크립트 실행은 프로젝트 루트(상위 폴더)에서 실행하는 것을 권장합니다.

예시:
```bash
# 루트 경로에서 실행
python utilly/final_pipeline_test.py
```
