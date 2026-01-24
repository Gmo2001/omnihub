# Omnihub Desktop Pipeline

PDF 문서를 GCS에 업로드하고, Document AI로 변환, 정규화(Normalization), 청킹(Chunking), 임베딩(Embedding)을 거쳐 **Vector Search**와 **Firestore**에 배포하는 전체 파이프라인입니다.

## 📁 폴더 구조

- **src/**: 파이프라인 단계별 실행 코드 및 유틸리티
- **config/**: 파이프라인 설정 파일
    - `omnihub_contract_v0.1.json`: 데이터 정규화 스키마
    - `drive_meta_virtual.json`: 가상 드라이브(폴더) 메타데이터 규칙
    - `vector_search_config.json`: Vertex AI Vector Search 설정
    - `publish_policy.json`: Firestore 컬렉션 및 문서 정책
- **data/**: 데이터 저장소 (Git 제외)
    - `raw/docai_result/`: Document AI 결과 JSON 원본
    - `processed/`: 단계별 처리 결과 (`canonical`, `chunks`, `embeddings`, `doc_records`)
    - `metadata/`: 기존 메타데이터

---

## 🚀 실행 순서 (Workflow)

프로젝트 **루트 폴더**(`05_omnihub_desktop`)에서 아래 명령어를 순서대로 실행하세요.

### 1. 문서 변환 (Ingestion)
GCS에 있는 문서를 Document AI Batch Process로 변환하여 JSON으로 다운로드합니다.
```bash
python src/step01_ingest_docai.py
```

### 2. 정규화 (Normalization)
DocAI 결과(JSON)를 읽어 Gemini로 메타데이터를 추출하고 표준 포맷(`canonical_content.jsonl`)으로 변환합니다.
```bash
python src/step02_normalize.py
```

### 3. 메타데이터 증강 (Augment & Record)
정규화된 데이터에 **가상 드라이브 정보(폴더 경로, URL 등)**를 입히고, Firestore 업용 `doc_records.jsonl`을 생성합니다.
- **사용 모듈**: `src/drive_meta_virtual.py` (결정론적 가상 메타데이터 생성기)
```bash
python src/step02b_augment_and_record.py
```

### 4. 청킹 (Chunking)
문서를 벡터 검색에 적합한 크기로 자릅니다.
```bash
python src/step03_chunk.py
```

### 5. 임베딩 (Embedding)
청크(Chunk)를 벡터(Embedding)로 변환하여 저장합니다.
```bash
python src/step04_embed.py
```

### 6. 배포 (Publish)
생성된 청크와 임베딩 데이터를 **Google Cloud Vertex AI (Vector Search)** 및 **Firestore**에 업로드합니다.
```bash
# 기본 모드 (Firestore만 업로드 - 빠름)
python src/step05_publish.py

# 전체 모드 (Vector Search 인덱싱 포함 - 20~40분 소요)
$env:PUBLISH_MODE="both"; python src/step05_publish.py
```
- `PUBLISH_MODE="firestore_only"` (기본값): Firestore 데이터만 갱신
- `PUBLISH_MODE="both"`: Vector Search Index 배포 및 데이터 업로드 포함

### 7. 문서 메타데이터 백필 (Backfill Docs)
`omnihub_docs` 컬렉션의 문서 메타데이터를 안전하게 갱신하거나 누락된 필드를 채웁니다.
```bash
python src/step06_backfill_firestore_docs.py --patch-missing-only
```

---

## 🛠️ 유틸리티 (Utilities)

파이프라인 운영 및 디버깅을 위한 보조 스크립트들입니다.

### 📊 모니터링
- **`src/monitor_docai.py`**: Document AI 처리 진행률을 실시간으로 확인합니다. (5분 주기 갱신)
    ```bash
    python src/monitor_docai.py
    ```
- **`src/check_docai_progress.py`**: GCS 버킷의 파일 개수(입력 vs 출력)를 1회 체크하여 진행 상황을 파악합니다.

### ✅ 데이터 검증
- **`src/check_normalization.py`**:
    - `canonical_content.jsonl` 파일에서 무작위로 100개를 샘플링하여 필수 필드(`summary`, `securityLevel`, `sizeBytes`, `mimeType`) 누락 여부를 검사합니다.
    ```bash
    python src/check_normalization.py
    ```
- **`src/verify_firestore.py`**:
    - Firestore의 `omnihub_docs` 컬렉션에 데이터가 정상적으로 들어갔는지 샘플 문서 하나를 조회하여 확인합니다.
    ```bash
    python src/verify_firestore.py
    ```

---

## ⚠️ 주의사항

1. **데이터 폴더 위치**: `data/raw/docai_result` 폴더에 Document AI 결과가 있어야 합니다.
2. **실행 경로**: 모든 스크립트는 **프로젝트 루트**(`05_omnihub_desktop`)에서 실행해야 합니다.
3. **환경 변수**: GCP 인증을 위해 `gcloud auth application-default login`이 선행되어야 합니다.
