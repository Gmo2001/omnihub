# 📘 AI-A 파이프라인 통합 및 연동 가이드 (Integration Roadmap)

본 문서는 `backend/app/services/ai_a/allragpipeline` 패키지가 옴니허브(OmniHub) 백엔드와 **"어떻게 유기적으로 연결되는지"**, 그리고 **"왜 코드가 수정되었는지"**를 AI-A 개발자에게 설명하기 위한 **상세 통합 문서**입니다.

---

## 📅 1. 통합 배경 및 목표 (Context & Goal)

### **[AS-IS] 기존 상황: "끊어진 연결 고리"**
1.  **Ingestion 단절**: 파일은 업로드되지만, 파일 내부(PDF/이미지 등)의 메타데이터(페이지 수, 저자 등)는 무시됨. `metadata_extractor.py`가 존재했으나 사용되지 않음.
2.  **Trigger 부재**: 파일이 드라이브에 도착해도 AI가 이를 알 수 없음. `run_docai_extract.py` 등은 사람이 수동으로 실행해야 하는 스크립트 형태였음.
3.  **성능 이슈**: 파일 1개가 들어와도 전체 DB를 다시 훑는 비효율적 구조 (O(N)).

### **[TO-BE] 개선 목표: "완전 자동화된 유기적 파이프라인"**
1.  **Ingest Service 강화**: 파일 업로드 시 `metadata_extractor`를 통해 내부 속성까지 추출하여 DB에 저장.
2.  **Analysis Service화**: AI 스크립트를 API/Webhook에서 호출 가능한 **서비스 클래스**로 리팩토링.
3.  **자동 트리거(Trigger)**: Webhook → Ingestion → **Pipeline Runner 자동 실행**.
4.  **성능 최적화**: 단일 문서 타격(O(1)) 및 병렬 처리 효율화.

---

## 🛠 2. 단계별 통합 과정 (Step-by-Step Changes)

### **Step 0. 사전 준비 & 통합 (Merged)**
- **행동**: `feature/ai-a` 브랜치의 파일들과 AI-A팀이 새로 추가한 `run_docai_extract.py`, `metadata_extractor.py`를 하나로 합침.
- **수정사항**: `run_docai_extract.py`는 단순 OCR 도구가 아니라, 이제 **Pipeline Runner의 핵심 구성요소(Phase A)**로 편입되었습니다.

### **Step 1. Ingestion 서비스 강화 (Metadata Extraction)**
- **목표**: 파일 겉면 정보뿐 아니라 **내부 정보(페이지 수, 저자 등)**를 추출.
- **적용**:
    - `app/services/ingestion_service.py`에서 스트리밍 중 `metadata_extractor`를 호출하도록 로직 추가.
    - **이유**: 페이지 수가 너무 많은 문서를 사전에 걸러내거나, 검색 품질을 높이기 위함.

### **Step 2. AI 서비스를 "호출 가능"하게 개조 (Refactoring)**
- **대상**: `run_docai_extract.py` 등 모든 파이프라인 스크립트.
- **변경**:
    - 단순 스크립트(`if __name__ == "__main__":`)에서 외부에서 호출 가능한 **Class & Method** 구조로 변경.
    - 특히 **`run(doc_id=...)`** 메서드를 표준화하여, 특정 파일 하나만 처리할 수 있도록 만듦.

### **Step 3. 파이프라인 트리거 연결 (The Organical Link)**
- **핵심**: 파일 업로드 완료 시점(Webhook/Ingestion)에 **`PipelineRunner`를 자동으로 깨움.**
- **데이터 흐름**:
    1.  **Drive Webhook**: "새 파일 도착!" 감지.
    2.  **Ingest Service**: GCS 저장 & 메타데이터 DB 기록.
    3.  **Analysis Trigger (NEW)**: `PipelineRunner` 호출 (`--doc_id` 전달).
    4.  **Pipeline Runner**: 
        *   → `A_run_docai_extract` (OCR)
        *   → `B_parallel_processing` (청킹, 요약, 엔티티)
        *   → `C_knowledge_graph` (지식 그래프)
        *   → `D_indexing` (벡터 DB 저장)

---

## 💻 3. AI-A 개발자가 알아야 할 코드 변경 사항

### **A. 성능 혁신: 전수 조사(O(N)) → 단일 타격(O(1))**
모든 파이프라인 스크립트(`extract_file_meta`, `run_docai_extract`, `build_profile` 등)에 **단일 문서 처리 모드**가 추가되었습니다.

*   **변경 전**: `run_batch()` → DB의 모든 파일을 Loop. (느림)
*   **변경 후**: `run(doc_id="...")` → **해당 ID의 문서 하나만** `get()`하여 처리. (빠름)

### **B. 안정성 강화: Race Condition 해결 (Phase B 순서 조정)**
`pipeline_runner.py` 내부에서 병렬 처리 순서를 조정했습니다.

*   **문제**: 청킹(`Split`)과 분석(`Extract/Summarize`)이 동시에 돌아가서, 분석기가 청크 파일을 못 찾는 에러 발생.
*   **해결**: 
    1.  **1조 (준비)**: `청킹` & `정책 분류` (완료 대기)
    2.  **2조 (분석)**: `요약` & `엔티티 추출` (청킹 완료 후 실행)

### **C. 리소스 최적화**
*   **Worker 수**: Cloud Run 4GiB 메모리를 활용하기 위해 `MAX_WORKERS`를 4 → **8**로 설정.

---

## 🌍 4. 필수 환경 변수 Checklist (.env)

통합된 파이프라인이 정상 작동하기 위해 다음 환경 변수가 필수적입니다.

**26.02.02노션** 참고 바람

