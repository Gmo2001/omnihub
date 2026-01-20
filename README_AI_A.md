# AI-A 개발자 인수인계 문서

## 1. 현재 프로젝트 상황 공유
안녕하세요, AI-A 개발자님. 현재 백엔드 시스템의 기초 공사가 완료된 상태입니다.

- **Backend Framework**: FastAPI 기반으로 구축되었습니다.
- **Project Structure**: `app/` 디렉토리 하위에 `routers`, `models`, `services`로 모듈화되어 있습니다.
- **Integration**:
    - **Google Drive**: 웹훅을 통해 파일 변경 사항을 감지하고 메타데이터를 가져오는 로직이 구현되어 있습니다.
    - **Firestore**: 사용자 및 파일 메타데이터를 저장하는 DB 연동이 되어 있습니다.
    - **Git Status**: 보안 이슈(Secret Key 노출)로 인한 Push 에러는 해결되었으며, 현재 `feature/back` 브랜치에서 작업 중입니다.

## 2. 맡아주실 업무: AI Service 구현
현재 `backend/app/services/ai_service.py` 파일은 껍데기(Mockup)만 구현되어 있습니다. 이 파일의 실제 로직 구현을 담당해주시면 됩니다.

### 목표
Google Drive에서 변경된 파일의 **텍스트 내용(Content)**을 넘겨받아, AI 모델(Gemini 등)을 통해 분석하고 **자동 분류 경로(Virtual Path)**와 **태그(Tags)**를 생성해야 합니다.

### 작업 파일 위치
- 파일: `backend/app/services/ai_service.py`
- 함수: `analyze_file_content(content: str, file_metadata: FileSchema) -> dict`

### 현재 코드 상태 (Mockup)
```python
async def analyze_file_content(content: str, file_metadata: FileSchema) -> dict:
    # ...
    # [Mockup] 프로토타입용 가짜 지능
    if "예산" in file_metadata.name:
        # ... 가상 결과 반환
```

### 구현 요구사항
1.  **LLM 연동**: `google-cloud-aiplatform` 또는 적절한 라이브러리를 사용하여 Gemini(혹은 다른 모델)와 연동해주세요.
2.  **Input**:
    - `content`: 파일의 추출된 텍스트 전체
    - `file_metadata`: 파일 이름, MIME type, 소유자 정보 등 (Context 보강용)
3.  **Output (Return Dict)**:
    - 아래 형식을 지켜주세요 (Firestore 저장 스키마와 일치해야 함):
      ```json
      {
        "virtual_path": "/부서/연도/카테고리",
        "tags": ["태그1", "태그2"],
        "suggestion_reason": "AI가 이 분류를 선택한 이유",
        "citation": "근거가 되는 본문 발췌",
        "ai_status": "completed"
      }
      ```
4.  **환경 변수**: API Key 등이 필요하면 `.env` 파일에 추가하고 공유해주세요 (`.env`는 git ignore 되어 있으므로 메신저로 전달).

## 3. 실행 방법
1.  가상환경 활성화: `backend/.venv/Scripts/activate`
2.  서버 실행: `uvicorn app.main:app --reload`
3.  테스트:
    - 현재 웹훅이나 트리거가 없어도, `main.py`나 별도 테스트 스크립트에서 `analyze_file_content`를 직접 호출하여 테스트 가능합니다.

잘 부탁드립니다!
