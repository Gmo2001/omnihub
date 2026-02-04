# OmniHub Frontend & Integration 가이드 (Up-to-Date)

이 문서는 OmniHub의 현재 프론트엔드/백엔드 통합 상태와 AI-A 관련 파이프라인 연동 현황을 설명합니다.

## 1. 현재 시스템 아키텍처 (Current State)

현재 OmniHub는 **"Hybrid Integration State"** 입니다.
- **Real (실제 동작)**: 구글 로그인, 드라이브 파일 탐색, 폴더 동기화(Sync), 파일 메타데이터 수집, 보안 로그 적재.
- **Mock (가상 동작)**: AI 분석 결과(지식 그래프, RAG 답변)는 현재 백엔드 라우터에서 **가상 데이터(Mock Data)**를 반환합니다.

### 데이터 흐름
`Frontend` -> `Backend Router` -> `Mock Data Generator` (AI Pipeline 미완성 시)
`Frontend` -> `Backend Router` -> `Real Service` (Auth, Drive, Logging)

---

## 2. 주요 기능 및 변경 사항 (Key Features)

### 2.1. Sync Queue & Active Monitoring
대량의 파일을 동기화할 때, 사용자가 진행 상황을 투명하게 알 수 있도록 **Sync Queue Panel**이 구현되었습니다.
- **Active Task**: 현재 처리 중인(Processing) 파일명 표시.
- **Up Next**: 대기 중인 파일 미리보기 (Queue Preview).
- **Recent Completed**: 최근 처리된 파일의 상태(Success/Skip/Fail)를 실시간 리스트업.
- **상태 정의**:
    - 🟢 **Success**: 정상 수집 및 AI 분석 트리거 완료.
    - ⚪ **Skip**: 드라이브 상에서 파일이 변경되지 않아 최적화를 위해 건너뜀 (Delta Sync).
    - 🔴 **Fail**: 지원하지 않는 포맷(Sheet/Slide)이거나 에러 발생.

### 2.2. Graceful Sync Cancellation (안전한 동기화 중단)
사용자가 긴 동기화 작업을 중간에 취소할 수 있는 기능입니다.
- **Safety First**: "즉시 강제 종료(Kill)"가 아니라 **"안전한 중단(Graceful Abort)"** 방식을 채택했습니다.
    - 현재 전송 중인 파일(예: 50% 진행된 500MB 영상)은 **끝까지 완료**하여 데이터 오염을 방지합니다.
    - 그 후 대기열의 나머지 파일들은 즉시 취소 처리됩니다.
- **UI Interaction**: `Stop Sync` 버튼 클릭 시 "Stopping..." 상태로 전환되며, 현재 파일이 완료되는 즉시 작업이 종료됩니다.

### 2.2. Indeterminate Loading State (AI Analysis)
동기화(Sync)가 끝나면 자동으로 AI 분석 단계로 넘어갑니다. 시간 예측이 어렵기 때문에 **상태 기반 로딩(State-based Loading)**을 사용합니다.
- **Flow**: `Idle` -> `Syncing (Files)` -> `Analyzing (AI Knowledge)` -> `Completed`
- **Persistence**: 새로고침을 해도 백엔드의 동기화 작업은 **중단되지 않고 백그라운드에서 끝까지 수행**됩니다.

### 2.3. System Kernel Panic Log (Security Dashboard)
AI 파이프라인이나 동기화 작업 중 발생하는 심각한 오류(Critical Error)는 사용자에게 팝업으로 띄우지 않고, **보안 대시보드**에 통합 기록됩니다.

- **저장소**: Firestore `sys_errors` 컬렉션
    - **구조**: `sys_errors` / **`YYYY-MM-DD` (Document)** / `logs` (Sub-collection)
    - **이유**: 날짜별 파티셔닝을 통해 조회 성능을 높이고, 오래된 로그 삭제(Retention Policy) 관리를 용이하게 함.
- **표시**: Admin > Security Dashboard > System Kernel Panic Log (오늘 날짜의 로그만 표시)
- **연동 파일**: `analysis_service.py` (AI), `ingest.py` (Sync) -> `log_system_error`

> **⚠️ 중요 (Environment Sync)**:
> 현재 로컬 개발 환경(`localhost`)에 적용된 최신 로그 로직(날짜별 저장)은 **Cloud Run 서버에 배포되기 전까지는 반영되지 않습니다.**
> 따라서 Cloud Run 배포 버전을 사용하는 프론트엔드에서는 최신 포맷으로 저장된 로그(오늘 날짜 폴더 내의 로그)가 보이지 않을 수 있습니다.
> (`verify_error_logging.py`로 생성된 테스트 로그는 Firestore에 잘 들어갔으나, 구버전 서버 코드는 이를 읽지 못할 수 있음)

---

## 3. Mock Data 구조 (AI Pipeline)

현재 백엔드(`backend/app/services/ai_a/allragpipeline/routers`)는 AI-A 팀의 모델이 준비되기 전까지, 프론트엔드 개발을 완벽히 지원하기 위해 **정교한 가상 파이프라인(Mock)**을 제공하고 있습니다.

### ✅ 가상 데이터 엔드포인트 (Mock Data Endpoints)
AI-A 모델 개발이 완료될 때까지, 프론트엔드는 다음 API를 호출하면 **고정된 가상 데이터(Static Mock Data)**를 응답받습니다.
1.  **지식 그래프 (`graph_api.py`)**: 복잡한 노드/링크 구조의 더미 데이터를 반환합니다.
2.  **RAG 검색 (`rag_api.py`)**: "OmniHub는..."으로 시작하는 고정된 답변 텍스트를 반환합니다.
3.  **문서 트리 (`tree_api.py`)**: AI 분석 결과로 가정된 임의의 트리 구조를 반환합니다.
4.  **문서 상세 (`card_docs_api.py`)**: 특정 문서 ID에 대해 항상 동일한 요약 및 분석 정보를 반환합니다.

---

## 4. Admin Console (문제 해결 가이드)

관리자 패널(`AdminUserManagement.tsx`) 사용 시 다음 사항을 주의해야 합니다.

### 4.1. Sync Manager (동기화 관리)가 비어 보이는 이유
- **Scope Restriction (Prototype)**: 현재 프로토타입 버전에서는 관리자 패널의 Sync Manager가 **"현재 로그인한 사용자(Admin)의 폴더"**만 조회하도록 제한되어 있습니다. (`files.py`의 `get_monitored_folders`가 `current_user`를 참조함)
- **Future Goal**: 실제 운영 단계에서는 `admin.py`를 통해 **전체 사용자의 동기화 현황**을 모니터링하고 제어하는 기능으로 확장될 예정입니다.
- **기능 제한**: 현재 "Stop Syncing(휴지통)" 버튼은 해당 폴더를 **구독 목록(Whitelist)에서 제거**하는 기능이며, **이미 실행 중인(Active Running) 백그라운드 작업을 즉시 강제 종료(Kill Process)하지는 않습니다.**

### 4.2. Sync Queue Panel (동기화 대기열)
- **Read-Only**: 이 패널은 백엔드의 진행 상황(`system_status` 컬렉션)을 시각화하여 보여주는 **뷰어(Viewer)**입니다. 여기서 동기화를 일시정지하거나 취소하는 조작 기능은 포함되어 있지 않습니다.
- **Localhost 제약**: 로컬 개발 환경에서 BigQuery 접속 권한이 없는 Credential을 사용할 경우, `System Status` 탭에서 BigQuery 항목이 **Error**로 표시될 수 있습니다. 이는 서버 코드가 아닌 로컬 인증 환경의 차이입니다.

---

## 5. 파일 관계 및 연동 (File Relationships)

### Frontend
-   `OmniHubContext.tsx`: 전역 상태 관리 (AI Status, Polling, User Auth).
-   `aiService.ts` -> **`dataService.ts`**: (변경됨) 이제 `aiService`가 아니라 `dataService`의 `BackendAPI`를 통해 백엔드와 통신합니다.
-   `SyncQueuePanel.tsx`: 동기화 대기열 시각화 컴포넌트.

### Backend
-   `ingest.py`: 파일 수집 및 `sync_folder_task` (백그라운드 워커).
-   `analysis_service.py`: `trigger_analysis` (AI 파이프라인 오케스트레이터).
-   `log_service.py`: 사용자 행동 로그(`logs`) 및 시스템 에러(`sys_errors`) 적재.

> **Note**: 추후 AI-A 모델이 완성되면, `mock_data.py`를 제거하고 실제 `PipelineRunner`의 결과를 DB에서 조회하도록 라우터만 수정하면 됩니다. 프론트엔드 수정은 최소화되어 있습니다.
