# 03_aihub Project Guide (Omnihub Docs Automation)

이 프로젝트는 **Omnihub 회계법인**의 문서 관리, 데이터 수집, 분류 및 메타데이터 생성을 위한 통합 자동화 도구입니다.

## 📂 Project Structure

```bash
03_aihub/   # (5-8단계 효율화 작업 해야함, 지금 너무 흐름이 없음)
├── src/                        # 실행 스크립트 모음
│   ├── step01_collect_links.py # [수집] AI-Hub 등 데이터셋 링크 크롤링/프로젝트 아이디어 수집용
│   ├── step02_scrape_items.py  # [수집] 수집된 링크의 상세 데이터 스크래핑/프로젝트 아이디어 수집용
│   ├── step03_classify_json.py # [분류] AI-Hub 다운로드한 데이터 중에 정답 라벨링 JSON 문서 중 '회계' 관련 파일 분류
│   ├── step04_simple_classify.py # [분류] 파일명 기반 폴더 분류 규칙 테스트
│   ├── step05_folder_gen.py    # [구축] Omnihub 표준 폴더 구조 생성
│   ├── step06_file_move.py     # [구축] 파일 이동 (CSV 매핑 기반)
│   ├── step07_filename_gen.py  # [구축] 파일명 정규화 및 변경
│   └── step08_metadata_gen.py  # [구축] AI 메타데이터 생성 및 JSONL 저장
├── data/                       # 데이터 저장소
│   ├── input/                  
│   │   └── json_raw/           # (step03용) 분류할 원본 JSON 파일들
│   ├── output/                 
│   │   ├── links/              # (step01 결과) 수집된 링크 리스트 (CSV)
│   │   ├── items/              # (step02 결과) 상세 스크래핑 결과 (CSV)
│   │   ├── accounting_list/    # (step03 결과) 분류된 회계 문서 목록 (CSV)
│   │   └── Omnihub 회계법인/   # (step05~08 결과) 최종 구축된 폴더 트리
│   └── mapping/                # 구축용 매핑 테이블
│       ├── file_move_list.csv  # 파일 이동 규칙 (파일명, 원본경로, 타겟경로)
│       └── filename_map.csv    # 파일명 변경 규칙
├── config/                     # 설정 파일
└── README.md                   # 프로젝트 가이드
```

## 🚀 Workflows

이 프로젝트는 크게 **수집/분류(Collection & Classification)** 단계와 **구축(Construction)** 단계로 나뉩니다.

### Part 1. 데이터 수집 및 분류 (선택 사항)
새로운 데이터를 수집하거나, 기존 파일 목록을 분석할 때 사용합니다.

1.  **링크 수집 (`step01`)**
    - `src/step01_collect_links.py` 실행
    - 결과: `data/output/links/aihub_result_YYYYMMDD.csv`

2.  **상세 스크래핑 (`step02`)**
    - `src/step02_scrape_items.py` 실행 (step01 결과 자동 로드)
    - 결과: `data/output/items/결과_YYYYMMDD.csv`

3.  **JSON 회계 문서 분류 (`step03`)**
    - `data/input/json_raw` 폴더에 JSON 파일들을 넣고 실행
    - 결과: `data/output/accounting_list/회계문서_목록.csv`

4.  **파일명 분류 시뮬레이션 (`step04`)**
    - `data/mapping/file_move_list.csv`를 읽어서 분류 규칙 적용 테스트
    - 결과: `data/output/simple_classify_result_YYYYMMDD.csv`

---

### Part 2. 데이터 구축 (메인)
정의된 데이터(`data/mapping`)를 기반으로 실제 폴더를 만들고 파일을 정리합니다. **반드시 순서대로 실행하세요.**

1.  **폴더 구조 생성 (`step05`)**
    - `data/output/Omnihub 회계법인` 아래에 표준 폴더 트리 생성.

2.  **파일 이동 (`step06`)**
    - `data/mapping/file_move_list.csv`를 읽어 실제 파일을 새 폴더 구조로 이동.
    - 절대 경로/상대 경로 자동 보정 지원.

3.  **파일명 변경 (`step07`)**
    - `data/mapping/filename_map.csv`를 읽어 파일명을 직관적인 한글 이름으로 변경.

4.  **AI 메타데이터 생성 (`step08`)**
    - 구축된 PDF 파일들을 AI(Gemini)로 분석.
    - 메타데이터(`Author`, `Summary` 등)를 생성하여 PDF 속성에 심고, 검색용 `omnihub_ai_metadata.jsonl` 파일 생성.

## ⚠️ Notes
- **상대 경로**: 프로젝트 폴더 전체를 어디로 이동해도 스크립트는 정상 작동합니다 (`pathlib` 사용).
- **데이터 준비**: `step06`, `step07` 실행 전 `data/mapping` 폴더에 CSV 파일이 올바르게 존재하는지 확인하세요.
