
# 📝 변경사항 리포트: 벡터 DB 적재 및 RAG 답변 성공 모델

**Commit Message**: `feat: RAG 백엔드 서비스의 초기 설정과 Firestore 기반 인증 및 데이터 저장소 기능을 구현합니다.`  
**Date**: 2026-02-03  

---

## 🛠️ 주요 수정 사항 (Key Changes)

### 1. 🔍 RAG 검색 엔진 및 생성기 (Search & Generation)
- **`app/rag/retriever.py`**
  - **Vector Search 필터링 개선**: `restricts`가 빈 리스트일 경우 `filter=None`을 전달하도록 수정하여 '검색 결과 0건' 문제 해결.
  - **Firestore 연동**: 문서 메타데이터 조회를 위해 `FirestoreRepo`를 활용.

- **`app/rag/generator.py`**
  - **Evidence 필드 매핑 수정**: Gemini 프롬프트 생성 시 `text` 키가 없을 경우 `snippet` 키를 확인하도록 Fallback 로직 추가 (답변 생성 불가 버그 해결).

### 2. 🔐 인증 및 보안 (Authentication)
- **`app/routers/auth_context.py`**
  - **기본값 환경변수 연동**: `Tenant-ID`가 헤더에 없을 경우 `os.getenv`를 통해 환경변수(`my-tenant`) 값을 사용하도록 수정. (Cloud Run 배포 환경 대응)

### 3. 💾 데이터 저장소 (Repository & Service)
- **`app/rag/firestore_repo.py`**
  - **Client Accessor 추가**: `get_firestore_client()` 메서드를 추가하여 GCS Fetch 로직에서 `db` 객체에 접근 가능하도록 수정.

- **`app/services/drive_service.py`**
  - **Google Drive 인증 로직 개선**: `dummy` 토큰 처리 로직을 `in` 연산자로 유연하게 변경하여 Service Account 인증이 올바르게 동작하도록 수정.
  - **Path Resolution**: 파일 경로 역추적(`resolve_full_path`) 시 디버그 로그 추가.

- **`app/services/ingestion_service.py`**
  - **File ID 반환**: `process_and_catalog_file` 함수가 `file_id`를 반환하도록 수정하여 파이프라인 연계성 확보.

### 4. 🧪 테스트 및 유틸리티 (Scripts)
- **`scripts/test/test_local_search.py`** (신규 생성)
  - 로컬 환경에서 Cloud Run과 동일한 설정으로 RAG 검색(Vector Search + Generation)을 테스트할 수 있는 스크립트 추가.
  - 실제 `VECTOR_DEPLOYED_INDEX_ID`를 강제 주입하여 연결 테스트.

- **`scripts/dev/clean_db.py`, `scripts/dev/clean_gcs.py`, `scripts/dev/run_ingest.py`** (신규 생성)
  - 개발 생산성을 위한 데이터 초기화 및 수동 인제스트 스크립트 추가.

---

## ✅ 해결된 이슈 (Resolved Issues)
1. **API 검색 결과 0건 문제**: Vector Search 필터 조건(`restricts`)을 `None`으로 해제하여 해결.
2. **Cloud Run 인증 실패**: `AuthContextMiddleware`가 기본값을 잘못 설정하던 문제를 환경변수 기반으로 수정.
3. **Gemini 답변 생성 실패**: "정보가 없습니다"라고 답하던 문제를 `snippet` 키 매핑으로 해결.
4. **GCS 접근 오류**: `get_firestore_client` 속성 에러 수정.
