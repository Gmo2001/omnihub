# BigQuery 파이프라인 & Risk Score 서비스 분석 문서

> **작성일**: 2026-02-06  
> **대상 폴더**: `bigquery/`, `risk_score/`

---

## 📋 목차

1. [개요](#-개요)
2. [BigQuery 파이프라인 (bigquery/)](#-bigquery-파이프라인-bigquery)
   - [폴더 구조](#폴더-구조)
   - [기능 목록](#기능-목록)
   - [데이터 흐름](#데이터-흐름)
3. [Risk Score 서비스 (risk_score/)](#-risk-score-서비스-risk_score)
   - [폴더 구조](#폴더-구조-1)
   - [기능 목록](#기능-목록-1)
   - [데이터 흐름](#데이터-흐름-1)
4. [전체 시스템 데이터 흐름](#-전체-시스템-데이터-흐름)
5. [핵심 비즈니스 로직](#-핵심-비즈니스-로직)

---

## 🎯 개요

이 시스템은 **사용자 행동 분석 기반 리스크 스코어링 파이프라인**입니다.

| 모듈 | 역할 |
|------|------|
| **bigquery/** | 원시 로그 데이터를 정제하고 피처 벡터를 생성하여 GCS로 내보내는 ETL 파이프라인 |
| **risk_score/** | 오토인코더 모델의 출력을 받아 리스크 점수를 계산하고 상태를 관리하는 이벤트 처리 서비스 |

---

## 📊 BigQuery 파이프라인 (bigquery/)

### 폴더 구조

```
bigquery/
├── config.yaml          # 프로젝트 설정 (데이터셋, 테이블, 파라미터)
├── main_app.py          # Flask 웹 서버 (Eventarc 트리거 수신)
├── pipeline.py          # 메인 ETL 파이프라인 로직
├── requirements.txt     # Python 의존성
├── Dockerfile           # 컨테이너 빌드 설정
├── .gitignore
└── sql/                 # SQL 쿼리 파일들
    ├── 01_clean_audit_view.sql      # 감사 로그 정제
    ├── 02_clean_system_view.sql     # 시스템 로그 정제
    ├── 03_user_5m_view.sql          # 사용자별 5분 집계
    ├── 04_dept_stats_ndays.sql      # 부서별 통계
    └── 05_feature_vector_table.sql  # 최종 피처 벡터
```

### 기능 목록

#### 1. **설정 관리** (`config.yaml`, `pipeline.py`)
- 프로젝트 ID, 데이터셋, 테이블명 관리
- 파라미터 설정 (n_days, action_types, location)
- SQL 쿼리 내 변수 치환 (`${...}` → 실제 값)

#### 2. **원시 데이터 정제** (`01_clean_audit_view.sql`, `02_clean_system_view.sql`)
- **감사 로그 정제**: JSON 파싱, actionType 매핑, ID 정규화
- **시스템 로그 정제**: 최근 N일 데이터만 필터링

#### 3. **피처 엔지니어링** (`03_user_5m_view.sql` ~ `05_feature_vector_table.sql`)
- **5분 윈도우 집계**: 사용자별 다운로드 횟수/초당 최대 다운로드 수
- **부서 통계 계산**: 부서별 평균/표준편차 계산
- **Z-Score 계산**: 사용자 행동의 부서 대비 이상도 측정

#### 4. **데이터 내보내기** (`pipeline.py`)
- 최신 windowStart 기준 데이터를 GCS로 CSV 내보내기
- traceId, contractVersion 메타데이터 추가

#### 5. **웹 서버** (`main_app.py`)
- Flask 기반 HTTP 엔드포인트
- POST `/` 요청 시 파이프라인 실행
- Eventarc/Cloud Run 통합용

### 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         BigQuery 데이터 파이프라인                                │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌────────────────────┐      ┌────────────────────┐
    │   audit_logs_raw   │      │ system_stdout_*    │
    │   (사용자 행동)      │      │ (시스템 이벤트)     │
    └─────────┬──────────┘      └─────────┬──────────┘
              │                           │
              ▼                           ▼
    ┌─────────────────────────────────────────────────┐
    │            01_clean_audit_view.sql              │
    │  • JSON 파싱 (actionType, fileId, userId 등)     │
    │  • actionType → actionTypeName 매핑             │
    │  • ID 정규화 (usr_, fil_ 접두사 추가)             │
    └─────────────────────┬───────────────────────────┘
                          │
    ┌─────────────────────────────────────────────────┐
    │           02_clean_system_view.sql              │
    │  • 최근 N일 시스템 로그만 필터링                  │
    │  • eventType, component, payload 추출           │
    └─────────────────────┬───────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────┐
    │             03_user_5m_view.sql                 │
    │  • 5분 윈도우 기준 집계                          │
    │  • userDownloads5m: 5분간 다운로드 수            │
    │  • maxDownloadsPerSec5m: 초당 최대 다운로드      │
    └─────────────────────┬───────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────┐
    │           04_dept_stats_ndays.sql               │
    │  • 부서별 평균 다운로드수 (deptMeanDownloads5m)   │
    │  • 부서별 표준편차 (deptStdDownloads5m)          │
    │  • 최근 N일 기준 계산                           │
    └─────────────────────┬───────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────┐
    │        05_feature_vector_table.sql              │
    │  • 사용자 데이터 + 부서 통계 JOIN                 │
    │  • z: Z-Score = (user - mean) / std             │
    │  • zPos: max(0, z) 양수 Z-Score만               │
    └─────────────────────┬───────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────┐
    │              GCS Export (CSV)                   │
    │  gs://aib-riskscore/inputs/realtime_vector_*.csv│
    │  • 최신 windowStart 기준 데이터                  │
    │  • traceId, contractVersion 포함                │
    └─────────────────────────────────────────────────┘
```

---

## 🛡️ Risk Score 서비스 (risk_score/)

### 폴더 구조

```
risk_score/
├── main.py              # Cloud Functions 엔트리포인트
├── processor.py         # GCS 이벤트 처리 로직
├── risk_logic.py        # 이벤트 리스크 계산 로직
├── risk_engine.py       # 누적 리스크 점수 & 상태 관리
├── stores.py            # GCP 서비스 클라이언트 (Firestore, GCS, BQ)
├── config.py            # 환경변수 설정 로더
├── utils.py             # 유틸리티 함수
├── local_watcher.py     # 로컬 개발용 GCS 폴링 감시자
├── requirements.txt     # Python 의존성
├── Dockerfile           # 컨테이너 빌드 설정
├── .env.example         # 환경변수 예시
├── .gitignore
├── __init__.py
└── scripts/             # 스크립트 폴더
```

### 기능 목록

#### 1. **Cloud Event 수신** (`main.py`)
- GCS 파일 생성 이벤트 수신 (Cloud Functions)
- `outputs/*.json` 패턴 파일만 처리
- 설정 로드 및 Stores 초기화

#### 2. **이벤트 처리** (`processor.py`)
- **멱등성 보장**: Firestore 트랜잭션으로 중복 처리 방지
- **GCS JSON 다운로드**: 오토인코더 출력 파일 읽기
- **리스크 계산**: `risk_logic.py` 호출
- **상태 업데이트**: Firestore에 사용자 최신 상태 저장
- **이벤트 기록**: BigQuery에 이벤트 로그 적재

#### 3. **리스크 로직** (`risk_logic.py`)
- **Base Score 계산**: reconError와 Z-Score 기반
  - reconError ≥ p95Threshold → base 최소 60
  - 그 외 → base = min(50, |z| * 10)
- **Add Score 계산**: metadata 기반
  - add1 = min(20, userDownloads5m / 10)
  - add2 = min(20, zPos * 5)
- **Multiplier 계산**: eventType 기반 가중치
  - MODEL_ANOMALY: 1.0
  - MASS_DOWNLOAD: 1.2
  - DENY_ACCESS: 1.5
  - NORMAL_ACTIVITY: 0.5
- **Event Risk 계산**: `(base + add) * mult` (0~100)

#### 4. **리스크 엔진** (`risk_engine.py`)
- **누적 점수 관리**: prevScore + eventRisk (0~100)
- **상태 결정** (defconMode):
  - riskScore ≥ 90 → `ALERT`
  - riskScore ≥ 50 → `WATCH`
  - riskScore < 50 → `SAFE`
- **상태 변경 감지**: stateChanged 플래그

#### 5. **데이터 저장소** (`stores.py`)
- **Firestore**:
  - 멱등성 키 관리 (`ingestions` 컬렉션)
  - 사용자 최신 상태 (`risk_users_latest` 컬렉션)
- **GCS**: JSON 파일 다운로드
- **BigQuery**: 리스크 이벤트 로그 적재

#### 6. **로컬 개발 지원** (`local_watcher.py`)
- GCS 버킷 폴링 방식 감시
- Cloud Event 없이 로컬에서 테스트 가능
- 기존 파일 스킵 옵션

### 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Risk Score 이벤트 처리 흐름                               │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────┐
    │   GCS: outputs/*.json                 │
    │   (오토인코더 모델 출력)               │
    │   {                                   │
    │     "userId": "usr_001",              │
    │     "reconError": 0.85,               │
    │     "eventType": "MODEL_ANOMALY",     │
    │     "trainMean": 0.12,                │
    │     "trainStd": 0.05,                 │
    │     "p95Threshold": 0.75,             │
    │     "metadata": {...}                 │
    │   }                                   │
    └──────────────────┬───────────────────┘
                       │
                       ▼ Cloud Event (Eventarc)
    ┌──────────────────────────────────────┐
    │           main.py                     │
    │   @functions_framework.cloud_event    │
    │   • outputs/*.json 필터링             │
    │   • Settings 로드                     │
    │   • Stores 초기화                     │
    └──────────────────┬───────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │         processor.py                  │
    │   process_gcs_output_json()           │
    └──────────────────┬───────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌───────────┐  ┌─────────┐
    │Firestore│  │   GCS     │  │Firestore│
    │(idem)   │  │ Download  │  │(users)  │
    │중복체크  │  │ JSON 읽기 │  │이전상태 │
    └────┬────┘  └─────┬─────┘  └────┬────┘
         │             │             │
         └─────────────┼─────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │          risk_logic.py                │
    │   build_event_risk_inputs()           │
    │   ┌────────────────────────────────┐  │
    │   │ base = f(reconError, z-score)  │  │
    │   │ add  = f(userDownloads, zPos)  │  │
    │   │ mult = f(eventType)            │  │
    │   │ eventRisk = (base+add)*mult    │  │
    │   └────────────────────────────────┘  │
    └──────────────────┬───────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │         risk_engine.py                │
    │   RiskScoreEngine.process_event()     │
    │   ┌────────────────────────────────┐  │
    │   │ riskScore = prev + eventRisk   │  │
    │   │ defconMode = SAFE/WATCH/ALERT  │  │
    │   │ stateChanged = (prev != new)   │  │
    │   └────────────────────────────────┘  │
    └──────────────────┬───────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
    ┌───────────────────┐      ┌───────────────────┐
    │    Firestore      │      │    BigQuery       │
    │ (risk_users_latest)│     │  (risk_events)    │
    │                   │      │                   │
    │ • userId          │      │ • ingestedAt      │
    │ • riskScore       │      │ • traceId         │
    │ • defconMode      │      │ • userId          │
    │ • eventRisk       │      │ • actionType      │
    │ • lastEventAt     │      │ • reconError      │
    │ • stateChanged    │      │ • riskScore       │
    └───────────────────┘      │ • state           │
                               │ • stateChanged    │
                               └───────────────────┘
```

---

## 🔄 전체 시스템 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              전체 시스템 아키텍처                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  사용자 행동  │ (다운로드, 조회, 삭제 등)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BigQuery (원시 로그)                          │
│  • audit_logs_raw_changelog (사용자 행동 로그)                    │
│  • run_googleapis_com_stdout_* (시스템 로그)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼ Eventarc 트리거
┌─────────────────────────────────────────────────────────────────┐
│               bigquery/ 파이프라인 (Cloud Run)                    │
│  • 로그 정제 → 피처 엔지니어링 → 피처 벡터 생성                     │
│  • 5분 윈도우 집계, 부서 통계, Z-Score 계산                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GCS (피처 벡터)                               │
│  gs://aib-riskscore/inputs/realtime_vector_*.csv                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼ Autoencoder 모델 추론
┌─────────────────────────────────────────────────────────────────┐
│                   autoencoder/ (별도 서비스)                      │
│  • 재구성 오류(reconError) 계산                                   │
│  • 이상 탐지 결과 출력                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GCS (모델 출력)                               │
│  gs://aib-riskscore/outputs/*.json                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼ Eventarc 트리거
┌─────────────────────────────────────────────────────────────────┐
│              risk_score/ 서비스 (Cloud Functions)                 │
│  • 이벤트 리스크 계산 (base + add) * mult                         │
│  • 누적 리스크 점수 관리                                          │
│  • 상태 결정 (SAFE → WATCH → ALERT)                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│       Firestore         │      │       BigQuery          │
│  (실시간 상태 저장)       │      │  (이벤트 로그 적재)      │
│                         │      │                         │
│  • risk_users_latest    │      │  • risk_events          │
│  • ingestions (멱등성)   │      │                         │
└─────────────────────────┘      └─────────────────────────┘
```

---

## 🧮 핵심 비즈니스 로직

### 리스크 점수 계산 공식

```python
# 1. Base Score (재구성 오류 기반)
if reconError >= p95Threshold:
    base = max(60, z_score * 10)  # 최소 60점
else:
    base = min(50, abs(z_score) * 10)

# 2. Add Score (사용자 행동 메타데이터 기반)
add1 = min(20, userDownloads5m / 10)
add2 = min(20, zPos * 5)
add = add1 + add2

# 3. Multiplier (이벤트 타입별 가중치)
mult_map = {
    "MODEL_ANOMALY": 1.0,
    "MASS_DOWNLOAD": 1.2,
    "DENY_ACCESS": 1.5,
    "NORMAL_ACTIVITY": 0.5
}
mult = mult_map.get(event_type, 1.0)

# 4. Event Risk (이번 이벤트의 위험도)
event_risk = clamp((base + add) * mult, 0, 100)

# 5. Risk Score (누적 위험도)
risk_score = clamp(prev_score + event_risk, 0, 100)

# 6. 상태 결정
if risk_score >= 90:
    defcon_mode = "ALERT"    # 🔴 경고
elif risk_score >= 50:
    defcon_mode = "WATCH"    # 🟡 주의
else:
    defcon_mode = "SAFE"     # 🟢 안전
```

### 주요 임계값

| 지표 | 임계값 | 설명 |
|------|--------|------|
| ALERT 상태 | riskScore ≥ 90 | 즉각 대응 필요 |
| WATCH 상태 | riskScore ≥ 50 | 모니터링 강화 |
| SAFE 상태 | riskScore < 50 | 정상 범위 |
| p95 기준 base | ≥ 60 | 상위 5% 이상치 |
| 최대 add | 40 | 메타데이터 보너스 상한 |

---

## 📝 참고 사항

- **멱등성 보장**: Firestore 트랜잭션으로 동일 파일 중복 처리 방지
- **GCS Generation**: 파일 버전으로 정확한 파일 식별
- **부서 정규화**: 부서 정보 없으면 `DEPT_UNKNOWN`으로 기본값 할당
- **ID 정규화**: `usr_`, `fil_` 접두사 자동 추가
