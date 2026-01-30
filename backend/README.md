# OmniHub Backend

OmniHub 프로젝트의 백엔드 서비스입니다. FastAPI를 기반으로 구축되었으며, Google Cloud Platform (Firestore, Vertex AI)과 연동하여 데이터 조회 및 AI(RAG) 기능을 제공합니다.

## 📁 디렉토리 구조

```
backend/
├── app/                    # 애플리케이션 소스 코드
│   ├── main.py             # 메인 앱 진입점 (FastAPI 앱 정의)
│   ├── config.py           # 설정 관리
│   ├── models.py           # 데이터 모델 (Pydantic)
│   ├── firestore_repo.py   # Firestore 데이터베이스 연동
│   ├── rag_gemini.py       # Gemini AI 연동 및 RAG 로직
│   ├── vector_search.py    # Vector Search 로직
│   └── embeddings.py       # 임베딩 생성 관련 유틸리티
├── run_server.ps1          # 서버 실행 스크립트 (환경변수 설정 포함)
└── requirements.txt        # 파이썬 의존성 패키지 목록
```

## 🚀 시작하기

### 1. 필수 조건

- Python 3.9 이상
- Google Cloud SDK 인증 (`gcloud auth login`, `gcloud auth application-default login`)

### 2. 설치

의존성 라이브러리를 설치합니다.

```CMD
pip install -r requirements.txt
```

### 3. 서버 실행

PowerShell 스크립트를 사용하여 환경 변수를 설정하고 서버를 실행합니다.

```powershell
.\run_server.ps1
```

서버가 실행되면 아래 주소에서 액세스할 수 있습니다.
- API 서버: `http://localhost:8000`
- API 문서 (Swagger UI): `http://localhost:8000/docs`

## ⚙️ 환경 설정 (Environment Variables)

`run_server.ps1` 파일 내에 기본 환경 변수가 설정되어 있습니다. 필요에 따라 수정하여 사용하세요.

| 변수명 | 설명 | 기본값 예시 |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP 프로젝트 ID | `jnu-rise-edu-147` |
| `FIRESTORE_DATABASE` | Firestore 데이터베이스 이름 | `(default)` |
| `VERTEX_LOCATION` | Vertex AI 리전 | `us-central1` |
| `ME_ENDPOINT_NAME` | Matching Engine (Vector Search) 엔드포인트 이름 | `omnihub_endpoint_v1` |
| `ME_DEPLOYED_INDEX_ID` | 배포된 인덱스 ID | `dep_1769150244` |
| `GEMINI_MODEL` | 사용할 Gemini 모델 버전 | `gemini-1.5-flash` |

## 🛠️ 주요 기능

- **Initial Data**: `/api/initial-data` 엔드포인트를 통해 초기 데이터를 로드합니다.
- **RAG (Search)**: 사용자의 질문에 대해 벡터 검색을 수행하고 Gemini를 통해 답변을 생성합니다.
- **Data Management**: Firestore와 연동하여 문서 및 드라이브 메타데이터를 관리합니다.
