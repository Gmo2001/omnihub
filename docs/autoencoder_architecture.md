# Autoencoder 모듈 아키텍처

## 📁 폴더 구조

```
app/omnihub/autoencoder/
├── __init__.py              # 패키지 초기화 파일
├── config.py                # 설정 상수 정의
├── train_autoencoder.py     # 모델 학습 스크립트
└── anomaly_scoring.py       # 이상 탐지 스코어링 스크립트
```

---

## 📄 파일별 설명

### 1. `config.py` - 설정 파일
모델과 관련된 모든 설정 상수를 중앙 관리합니다.

| 상수 | 값 | 설명 |
|------|-----|------|
| `INPUT_DIM` | 2 | 입력 피처 차원 수 |
| `LATENT_DIM` | 1 | 잠재 공간(Latent Space) 차원 수 |
| `RISK_THRESHOLD` | 3.0 | 위험 판단 기준 (Z-score) |
| `MODEL_PATH` | `models/autoencoder.h5` | 학습된 모델 저장 경로 |
| `SCALER_PATH` | `models/scaler.pkl` | StandardScaler 저장 경로 |
| `BASELINE_PATH` | `models/baseline.json` | 기준값(mean, std, p95) 저장 경로 |

---

### 2. `train_autoencoder.py` - 학습 스크립트
Autoencoder 모델을 학습시키고 아티팩트를 저장합니다.

#### 주요 함수

| 함수 | 설명 |
|------|------|
| `build_autoencoder(input_dim, latent_dim)` | Encoder-Decoder 구조의 Autoencoder 모델 생성 |
| `fit_autoencoder(X: np.ndarray)` | 데이터 스케일링, 학습, Baseline 계산 |
| `save_artifacts(model, scaler, baseline)` | 학습 결과물(모델, 스케일러, 기준값) 저장 |
| `main()` | 메인 실행 함수 (샘플 데이터 생성 및 학습) |

#### 모델 아키텍처
```
Encoder:
  Dense(64, ReLU) → Dropout(0.2) → Dense(32, ReLU) → Dense(latent_dim, ReLU)

Decoder:
  Dense(32, ReLU) → Dense(64, ReLU) → Dropout(0.2) → Dense(input_dim, Sigmoid)
```

---

### 3. `anomaly_scoring.py` - 이상 탐지 스코어링
학습된 모델을 사용하여 새로운 데이터의 이상 여부를 판단합니다.

#### 주요 함수

| 함수 | 설명 |
|------|------|
| `load_artifacts()` | 저장된 모델, 스케일러, 기준값 로드 |
| `compute_recon_error(model, X_scaled)` | 재구성 오차(Reconstruction Error) 계산 |
| `score_batch(model, scaler, baseline, X_raw)` | 배치 데이터에 대한 Z-score 및 이상 레벨 계산 |
| `run(input_path, output_path)` | CSV 파일 입력 → 이상 탐지 → 결과 CSV 출력 |

#### 이상 레벨 기준

| Z-score | Level |
|---------|-------|
| ≥ 3.0 | **ALERT** (경고) |
| ≥ 2.0 | **WATCH** (주의) |
| < 2.0 | **NORMAL** (정상) |

---

## 🔄 데이터 흐름도

### Phase 1: 모델 학습 (Training)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRAINING PHASE                                     │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌──────────────┐
     │  Raw Data    │  (BigQuery 또는 샘플 데이터)
     │  (n, 2)      │
     └──────┬───────┘
            │
            ▼
┌───────────────────────┐
│   StandardScaler      │  fit_transform()
│   (정규화)            │
└───────────┬───────────┘
            │
            ▼
     ┌──────────────┐
     │ Scaled Data  │
     │ (n, 2)       │
     └──────┬───────┘
            │
            ▼
┌───────────────────────┐
│   Train/Val Split     │  (80% / 20%)
│                       │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Autoencoder Model   │
│   ┌───────────────┐   │
│   │   Encoder     │   │
│   │  64→32→1      │   │
│   └───────┬───────┘   │
│           │           │
│   ┌───────▼───────┐   │
│   │   Decoder     │   │
│   │  1→32→64→2    │   │
│   └───────────────┘   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Baseline 계산       │
│   - train_mean        │
│   - train_std         │
│   - p95_threshold     │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────────────────────────────┐
│                 ARTIFACTS                      │
│  ┌─────────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ .h5 모델   │ │ .pkl     │ │ .json       │ │
│  │ autoencoder│ │ scaler   │ │ baseline    │ │
│  └─────────────┘ └──────────┘ └─────────────┘ │
└───────────────────────────────────────────────┘
```

---

### Phase 2: 이상 탐지 (Inference)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INFERENCE PHASE                                     │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌──────────────┐
     │  Input CSV   │  (새로운 데이터)
     │  - columns:  │
     │  userDownloads5m, zPos
     └──────┬───────┘
            │
            ▼
┌───────────────────────────────────────────────┐
│             Load Artifacts                     │
│  ┌─────────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ .h5 모델   │ │ .pkl     │ │ .json       │ │
│  │ autoencoder│ │ scaler   │ │ baseline    │ │
│  └─────────────┘ └──────────┘ └─────────────┘ │
└───────────────────┬───────────────────────────┘
                    │
                    ▼
┌───────────────────────┐
│   StandardScaler      │  transform() (학습된 스케일러 사용)
│   (정규화)            │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Model Predict       │
│   X_pred = model(X)   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Reconstruction      │
│   Error 계산          │
│   MSE(X, X_pred)      │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Z-score 계산        │
│   z = (err - mean)    │
│       / std           │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Level 분류          │
│   ┌─────────────────┐ │
│   │ z ≥ 3.0 → ALERT │ │
│   │ z ≥ 2.0 → WATCH │ │
│   │ z < 2.0 → NORMAL│ │
│   └─────────────────┘ │
└───────────┬───────────┘
            │
            ▼
     ┌──────────────┐
     │  Output CSV  │
     │  + recon_error
     │  + is_anomaly│
     └──────────────┘
```

---

## 📊 전체 시스템 연동 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FULL SYSTEM FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────┘

 ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
 │   BigQuery   │ ───▶ │  Autoencoder │ ───▶ │  Risk Score  │
 │  (Raw Data)  │      │  (Anomaly)   │      │  (최종 점수) │
 └──────────────┘      └──────────────┘      └──────────────┘
        │                     │                     │
        │                     │                     │
        ▼                     ▼                     ▼
 ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
 │ bigquery/    │      │ autoencoder/ │      │ risk_score/  │
 │ - query.py   │      │ - train_*.py │      │ - risk_logic │
 │ - export.py  │      │ - anomaly_*  │      │   .py        │
 └──────────────┘      └──────────────┘      └──────────────┘
```

---

## 🛠️ 사용 방법

### 1. 모델 학습
```bash
python -m app.omnihub.autoencoder.train_autoencoder
```

### 2. 이상 탐지 실행
```bash
python -m app.omnihub.autoencoder.anomaly_scoring --input data.csv --output result.csv
```

---

## 📌 주요 특징

1. **비지도 학습**: 라벨 없이 정상 패턴을 학습
2. **재구성 오차 기반**: 정상 데이터는 잘 복원되고, 이상 데이터는 복원이 어려움
3. **Z-score 정규화**: 학습 데이터 기준으로 표준화된 이상 점수 산출
4. **3단계 레벨 분류**: NORMAL / WATCH / ALERT

---

## 📅 작성 정보
- **작성일**: 2026-02-06
- **작성자**: Antigravity AI Assistant
