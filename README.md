# 🤝 OmniHub 팀 협업 및 개발 가이드

이 문서는 프로젝트의 전체 구조와 협업 방식을 설명합니다.
**Part 1**에서는 백엔드팀이 구축한 상세 파이프라인(Phase 1~4)을 설명하고,
**Part 2**에서는 각 팀(AI-A, AI-B, Frontend)이 참고해야 할 개발 가이드를 제공합니다.

---

# Part 1. Backend Data Pipeline (Organic Flow)

백엔드 팀이 구축해둔 데이터 흐름입니다. 다음 4단계(Phase)를 거쳐 데이터가 준비됩니다.

1.  **Phase 1**: 관리자/사용자 권한 시스템 구축 (완료)
2.  **Phase 2**: 구글 드라이브 -> GCS 스트리밍 파이프라인 (완료)
3.  **Phase 3**: Document AI 연동 및 Raw Data Handoff (완료)
4.  **Phase 4**: 활동 로그 BigQuery 파이프라인 (완료)

## **Phase 1**: 관리자/사용자 권한 시스템 구축 (완료)

이 단계는 모든 데이터 접근의 관문이 되는 가장 중요한 단계입니다. **Google OAuth**를 통해 신원을 확인하고, **Firestore**에 사용자 정보를 저장하며, 시스템 내부에서 사용할 **JWT**를 발급하는 과정입니다.

## **관련 파일 및 역할**

| **파일 경로** | **역할** | **핵심 기능** |
| --- | --- | --- |
| **app/routers/auth.py** | **인증 관제탑** | Google OAuth 연동, 콜백 처리, JWT 발급, 로그인 로그 기록 |
| **app/models/user.py** | **데이터 구조** | User 스키마 정의 (`role`, `google_access_token`, `department` 등) |
| **app/core/config.py** | **설정 관리** | Google Client ID, `SUPER_ADMIN_EMAIL` 설정 값 제공 |
| **app/dependencies.py** | **보안 문지기** | API 호출 시 JWT 토큰 검증, **current_user** 주입 |
| **app/routers/admin.py** | **관리자 기능** | 사용자 권한/부서 변경 (Admin Role 필요) |
| **app/services/log_service.py** | **기록** | 로그인 성공 시 감사 로그(Audit Log) 적재 |

## **상세 진행 과정 설명**

**1단계: 로그인 요청 및 리다이렉트**

- 사용자가 "Google로 로그인" 버튼을 누르면 **app/routers/auth.py**의 **login** 엔드포인트가 호출됩니다.
- 서버는 Google의 인증 페이지 URL을 생성하여 프론트엔드에 전달합니다. 이때 `scope` 파라미터에 `drive.readonly` 등을 포함하여 추후 파일 접근 권한을 미리 요청합니다.

**2단계: Google 인증 및 동의**

- 사용자는 Google 화면에서 로그인을 하고, OmniHub가 내 드라이브 파일을 보거나 관리하는 것에 동의합니다.

**3단계: 토큰 교환 (Callback)**

- Google은 사용자를 다시 OmniHub 백엔드의 `/auth/callback` 주소로 보냅니다. 이때 일회용 `code`를 같이 줍니다.
- 백엔드는 이 `code`를 가지고 Google에게 다시 요청하여, 실제로 사용할 수 있는 **Google Access Token**과 **Refresh Token**을 받아옵니다.

**4단계: 사용자 정보 관리 (DB Upsert)**

- 받아온 이메일 주소를 Key로 사용하여 Firestore(**users** 컬렉션)를 조회합니다.
- **Role 부여 로직**:
    - 만약 이메일이 **config.py**에 설정된 `SUPER_ADMIN_EMAIL`과 같다면, 즉시 `role="admin"`을 부여합니다.
    - 그 외에는 기본적으로 `role="user"`가 됩니다.
- 사용자의 정보(이름, 사진)와 가장 중요한 **Google Token들(암호화 권장)**을 DB에 저장합니다. 이 토큰은 나중에 Phase 2(파일 스트리밍)에서 사용됩니다.

**5단계: 활동 로그 기록 (Phase 4 연동)**

- **log_service.py**를 호출하여 "누가 언제 로그인했다"는 사실을 Firestore `logs` 컬렉션에 남깁니다. 이것은 나중에 BigQuery로 넘어가 분석 데이터가 됩니다.

**6단계: 서비스 이용권(JWT) 발급**

- 모든 처리가 끝나면 백엔드는 "OmniHub 내부 통행증"인 **JWT(Json Web Token)**을 발급합니다.
- 이 토큰 안에는 `uid`, `email`, 그리고 `role` 정보가 들어있어서, 이후 프론트엔드가 다른 API를 호출할 때마다 매번 DB를 뒤지지 않고도 권한을 확인할 수 있게 해줍니다.

---

## **Phase 2**: 구글 드라이브 -> GCS 스트리밍 파이프라인 (완료)

Phase 2는 사용자의 Google Drive에 있는 파일을 백엔드 서버의 디스크에 저장하지 않고, 메모리 스트림(Memory Stream)을 통해 곧바로 회사의 Google Cloud Storage(GCS)로 안전하게 이관하는 단계입니다.

## **관련 파일 및 역할**

| **파일 경로** | **역할** | **핵심 기능** |
| --- | --- | --- |
| **app/routers/ingest.py** | **접수 창구** | 파일 Ingest 요청 수신 (`POST /drive/ingest`), 결과 반환 |
| **app/services/drive_service.py** | **나르미 (Core)** | Google Drive API 연결, 파일 스트림 다운로드, GCS 업로드 파이프라인 |
| **app/models/user.py** | **열쇠 꾸러미** | Firestore에 저장된 `google_access_token`을 제공하여 드라이브 잠금 해제 |
| **app/services/log_service.py** | **기록** | 파일 전송 성공 여부 및 파일 크기/유형 로그 기록 |
| **app/core/gcp_clients.py** | **인프라 연결** | Google Cloud Storage 클라이언트 초기화 |

## **상세 진행 과정 설명**

**1단계: 파일 전송 요청 (ingest.py)**

- 프론트엔드에서 사용자가 파일을 선택하면 파일의 ID(예: `1ABC...`)만 백엔드로 보냅니다. 파일 자체를 업로드하는 것이 아닙니다.

**2단계: 권한 및 토큰 로드 (dependencies.py)**

- API는 요청을 보낸 사용자가 누구인지 확인(**current_user**)합니다.
- 이때 가장 중요한 것은 Phase 1에서 DB에 저장해둔 **`google_access_token`**을 꺼내오는 것입니다.

**3단계: 드라이브 연결 (drive_service.py)**

- **get_user_drive_service()** 함수가 사용자의 토큰을 이용해 Google Drive API와 연결합니다.
- 만약 토큰이 만료되었다면 `refresh_token`을 이용해 자동으로 갱신합니다.

**4단계: 메모리 스트리밍 (핵심 기술)**

- **다운로드 스트림**: 드라이브에서 파일을 조금씩 읽어오는 빨대(`io.BytesIO` 등)를 꽂습니다.
- **업로드 스트림**: 동시에 GCS 버킷(`omnihub-raw`)으로 데이터를 쏘아 보내는 빨대를 꽂습니다.
- **파이프라인**: 백엔드 서버는 이 두 빨대를 연결만 해줍니다. 파일 데이터는 서버 디스크에 닿지 않고 **메모리를 스쳐 지나가며 GCS로 이동**합니다.
    - *장점 1*: 서버 디스크 용량 부족 문제 해결
    - *장점 2*: 보안성 강화 (서버에 파일 흔적이 남지 않음)
    - *특이사항*: Google Docs/Sheets 같은 Workspace 파일은 자동으로 PDF로 변환하여 가져옵니다.

**⇒ P. 메모리 스트리밍으로 가져올 수 있는 제한사항이 존재**

- **네트워크 의존성**: 전송 중에 인터넷이 끊기면 처음부터 다시 보내야 할 수 있습니다. (Resumable Upload로 보완 가능)
- **초대용량 (수 GB)**: Stream 자체는 문제가 없으나, Document AI의 **20MB 제한(온라인 처리)**에 걸립니다. 이 경우 자동으로 비동기 배치 모드로 넘어가야 합니다.

**5단계: 로그 및 완료 반환**

- 전송이 끝나면 GCS의 주소(`gs://...`)를 받습니다.
- **log_service.py**를 호출하여 "어떤 파일을 GCS 어디에 저장했다"는 증거를 남깁니다.
- 사용자에게는 "성공했습니다"라는 메시지를 보냅니다.

---

## **Phase 3**: Document AI 연동 및 Raw Data Handoff (완료)

Phase 3는 GCS에 저장된 파일을 **Google Document AI**로 처리하여, AI-A팀이 활용할 수 있는 **정형화된 JSON(`docai_output.json`)**으로 변환하고 이를 **Firestore**에 저장(Handoff)하는 단계입니다.

## **관련 파일 및 역할**

| **파일 경로** | **역할** | **핵심 기능** |
| --- | --- | --- |
| **app/routers/ingest.py** | **오케스트레이터** | 배치 처리 요청 수신 (`POST /drive/process/batch`), 결과 DB 저장 지휘 |
| **app/services/docai_service.py** | **통역사 (Core)** | Document AI API 호출, 복잡한 Proto 결과를 `docai_output.json` 스키마로 번역 |
| **app/core/config.py** | **설정** | `DOCAI_LOCATION`, `DOCAI_PROCESSOR_ID` 등 필수 설정값 제공 |
| **app/core/gcp_clients.py** | **저장소 연결** | Firestore 클라이언트 (`db`) 제공 |
| **app/services/log_service.py** | **기록** | 배치 처리 결과(성공/실패 건수) 로그 기록 |

## **상세 진행 과정 설명**

**1단계: 배치 처리 요청 (ingest.py)**

- Phase 2에서 GCS에 파일을 올린 후, 프론트엔드(또는 자동화 스크립트)가 "이 파일들 AI로 처리해 주세요"라고 요청합니다.
- 이때 파일의 위치(`gcs_uri`)와 종류(`mime_type`) 리스트를 함께 보냅니다.

**2단계: Document AI 호출 및 변환 (docai_service.py)**

- **호출**: Google Document AI에게 "이 GCS에 있는 파일을 분석해 줘"라고 요청합니다. **config.py**에 설정된 `PROCESSOR_ID`를 사용합니다.
- **분석**: Google AI가 OCR(광학 문자 인식) 및 문서 구조 분석을 수행하여 결과를 돌려줍니다. 이때 돌아오는 데이터 형태(Proto)는 매우 복잡합니다.
- **변환 (Mapping)**:
    - 복잡한 Proto 데이터를 AI-A 팀이 요구한 **깔끔한 JSON (`docai_output.json`)**으로 변환합니다.
    - 페이지별 텍스트, 문단(Block), 좌표(BBox), 신뢰도(Confidence) 등 핵심 정보만 추출합니다.

**3단계: 결과 이관/저장 (`Firestore`)**

- 변환된 JSON 데이터를 **Firestore의 `docai_results` 컬렉션**에 그대로 저장합니다.
- **Handoff Point**: 백엔드의 역할은 여기까지입니다. 이제 AI-A 팀은 이 컬렉션에 쌓인 데이터를 가져가서 지지고 볶고(Normalization, Chunking, Vectorizing) 마음대로 요리할 수 있습니다.

**4단계: 로그 및 완료**

- "총 10건 중 9건 성공, 1건 실패"와 같은 요약 정보를 `log_service`를 통해 기록하고, 사용자에게 완료 응답을 보냅니다.

---

## **Phase 4**: 활동 로그 BigQuery 파이프라인 (완료)

Phase 4는 사용자의 모든 활동(Login, Ingest, Process)을 기록하여 **Firestore**에 적재하고, 이를 **Firebase Extension**을 통해 **BigQuery**로 실시간 동기화하여 AI-B(분석 AI)가 활용할 수 있게 만드는 단계입니다.

## **관련 파일 및 역할**

| **파일 경로** | **역할** | **핵심 기능** |
| --- | --- | --- |
| **app/services/log_service.py** | **서기 (Recorder)** | 활동 내역을 정형화된 포맷(User, Action, Resource)으로 변환하여 Firestore에 기록 |
| **app/routers/auth.py** | **로그인 감지** | 로그인 성공 시점(**auth_callback**)에 **log_activity** 호출 |
| **app/routers/ingest.py** | **작업 감지** | 파일 업로드 및 AI 처리 시점에 **log_activity** 호출 |
| **app/core/gcp_clients.py** | **저장소 연결** | Firestore 클라이언트 (`db`) 제공 |
| **Firebase Extension** | **배송 기사 (Sync)** | Firestore `logs` 컬렉션의 변경사항을 감지하여 BigQuery 테이블로 자동 복사 (코드 외 설정) |

## **상세 진행 과정 설명**

**1단계: 사용자 활동 발생 및 감지**

- 사용자가 로그인을 하거나(**auth.py**), 파일을 업로드(**ingest.py**)하면 각 라우터가 이를 감지합니다.
- 비즈니스 로직(로그인 처리, 파일 전송 등)이 성공적으로 완료된 직후에 로그 기록을 시도합니다.

**2단계: 로그 구조화 및 적재 (log_service.py)**

- 라우터는 **log_service.py**를 호출하며 "누가(User), 무엇을(Action), 어떻게(Details) 했다"는 정보를 넘깁니다.
- **Log Service**는 이 정보를 분석하기 좋은 형태로 다듬습니다.
    - 특히 Phase 1에서 구축한 **부서(Department)** 정보를 반드시 포함시킵니다. (부서별 사용량 분석을 위해)
- 다듬어진 데이터는 **Firestore의 `logs` 컬렉션**에 저장됩니다. Firestore는 여기서 일종의 **빠른 버퍼(Buffer)** 역할을 합니다.

**3단계: BigQuery 동기화 (Firebase Extension)**

- 이 단계는 우리가 짠 파이썬 코드가 아니라, **GCP 인프라 시스템**이 수행합니다.
- 미리 설정해둔 **"Stream Collections to BigQuery"** 확장 프로그램이 `logs` 컬렉션을 24시간 감시합니다.
- 새로운 로그가 들어오면, 즉시 그것을 낚아채서 **BigQuery**의 테이블(`omnihub_logs`)에 집어넣습니다.

**4단계: 데이터 분석 (AI-B 활용)**

- 이제 데이터는 분석 전용 웨어하우스인 BigQuery에 안전하게 저장되었습니다.
- AI-B 팀이나 데이터 분석가는 SQL을 사용하여 마음껏 데이터를 조회하고, 대시보드를 만들거나 AI 모델을 학습시킬 수 있습니다.

---

# Part 2. Developer Guides (Team Roles)

각 팀은 위 파이프라인에서 처리된 데이터를 바탕으로 본인의 영역을 개발해주시면 됩니다.

## 🤖 AI-A 팀 (Document Analysis)
**"백엔드가 차려준 밥상(1차 가공 데이터)을 맛있게 요리(구조화/분석)해주세요."**

### 📂 작업 영역
*   **디렉토리**: `backend/app/services/ai_a/`
*   **핵심 파일 (예시)**: `analysis_service.py`
    > **Note**: 나열된 파일은 예시입니다. 개발 진행 과정에서 자유롭게 파일을 추가/수정하고, 추후 GitHub에 올릴 때 본 README를 업데이트해주세요.

### 🛠️ 개발 가이드
1.  **Input 데이터**: 백엔드로부터 `Document AI 결과` + `파일 메타데이터`를 전달받게 됩니다.
2.  **LLM 활용**: 전달받은 텍스트 데이터를 Gemini 등을 활용해 분석하는 로직을 구현하세요.
3.  **Output 규격 정의**:
    *   분석 결과(태그, 요약, 카테고리 등)를 담을 JSON 스키마를 **직접 정의**하고 백엔드 팀에 공유해주세요.
    *   정의한 스키마대로 결과가 나오도록 `analyze_text()` 함수 등을 구현하면 됩니다.

---

## 🗣️ AI-B 팀 (Generative & Chat)
**"AI-A 팀이 정리한 데이터를 활용해 사용자와 대화하는 서비스를 만들어주세요."**

### 📂 작업 영역
*   **디렉토리**: `backend/app/services/ai_b/`
*   **핵심 파일 (예시)**: `chat_service.py`, `rag_service.py`
    > **Note**: 나열된 파일은 예시입니다. 개발 진행 과정에서 자유롭게 파일을 추가/수정하고, 추후 GitHub에 올릴 때 본 README를 업데이트해주세요.

### 🛠️ 개발 가이드
1.  **데이터 활용**: Firestore에 저장된 분석 완료 데이터(AI-A 결과물)를 활용합니다.
2.  **RAG 구축**: 사용자의 질문에 답변하기 위해 필요한 데이터를 검색(Retrieval)하고 생성(Generation)하는 파이프라인을 구축하세요.
3.  **API 연동**: 프론트엔드와 통신할 채팅 관련 로직을 담당합니다.

---

## 🎨 Frontend 팀 (User Interface)
**"현재 파일들은 자리만 잡아둔 상태(Placeholder)입니다. 추후 다음 기능들을 구현해주세요."**

### 📂 작업 영역
*   **디렉토리**: `frontend/` (현재는 기본 파일만 존재)
    > **Note**: 현재 프론트엔드는 폴더 구조만 존재합니다.

### 🛠️ 개발 가이드
*   **현재 상태**: 파일 구조만 잡혀있으며, 실제 로직은 비어있습니다.
*   **추후 구현 목표**:
    1.  **Dashboard**: 파일 업로드 현황 및 분석 상태(`processing` -> `completed`) 모니터링.
    2.  **Result View**: AI-A가 분석한 태그 및 메타데이터를 보여주고 수정하는 UI.
    3.  **Chat Interface**: AI-B와 대화할 수 있는 채팅창 구현.

---

## 📂 최종 파일 구조 제안

```bash
backend/app/
├── routers/
│   ├── drive_webhook.py  # [Backend] Phase 1 
│   ├── ingest.py         # [Backend] Phase 2~3 
│   └── chat.py           # [AI-B 협업] Phase 4 이후
├── services/
│   ├── ingestion_service.py # [Backend] GCS Upload
│   ├── docai_service.py     # [Backend] DocAI
│   ├── ai_a/             # [AI-A Workspace]
│   │   └── analysis_service.py
│   └── ai_b/             # [AI-B Workspace]
│       ├── chat_service.py
│       └── rag_service.py
└── models/               # Shared Schemas
```
