import argparse
import json
import numpy as np
import joblib
import pandas as pd
from tensorflow import keras
from config import MODEL_PATH, SCALER_PATH, BASELINE_PATH

def load_artifacts():
    model = keras.models.load_model(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(BASELINE_PATH, "r") as f:
        baseline = json.load(f)
    return model, scaler, baseline

def compute_reconError(model, X_scaled):
    X_pred = model.predict(X_scaled)
    return np.mean((X_scaled - X_pred) ** 2, axis=1)

def run(input_path: str, output_path: str):
    # 1) CSV 읽기
    df = pd.read_csv(input_path)

    # 2) 모델 / 스케일러 / 기준값 불러오기
    model, scaler, baseline = load_artifacts()
    
    # baseline.json 키 적용
    trainMean = baseline.get("trainMean")
    trainStd = baseline.get("trainStd")
    p95Threshold = baseline.get("p95Threshold")

    # 3) 피처 선택
    feature_cols = ["userDownloads5m", "zPos"]
    X = df[feature_cols]
    
    # 4) 스케일링 및 재구성 오차 계산
    X_scaled = scaler.transform(X)
    reconErrors = compute_reconError(model, X_scaled)

    # 5) 결과 데이터 가공 (추가 로직 없이 매핑만 수행)
    json_results = []
    for i in range(len(df)):
        row = df.iloc[i]
        current_error = float(reconErrors[i])
        
        # eventType 판별 (우선순위 적용)
        deny_count = row.get('denyCount5m', 0)
        deny_ratio = row.get('denyRatio5m', 0.0)
        downloads = row.get('userDownloads5m', 0.0)

        if deny_count >= 1 or deny_ratio >= 0.2:
            event_type_str = "DENY_ACCESS"
        elif downloads >= 5:
            event_type_str = "MASS_DOWNLOAD"
        elif current_error >= p95Threshold:
            event_type_str = "MODEL_ANOMALY"
        else:
            event_type_str = "NORMAL_ACTIVITY"
            
        record = {
            "traceId": str(row.get('traceId', '')),
            "windowStart": str(row.get('windowStart', '')),
            "userId": str(row.get('userId', '')),
            "eventType": event_type_str,
            "trainMean": trainMean,
            "trainStd": trainStd,
            "p95Threshold": p95Threshold,
            "reconError": current_error,
            "metadata": {
                "userDownloads5m": float(downloads),
                "zPos": float(row.get('zPos', 0.0))
            }
        }
        json_results.append(record)

    # 6) JSON 파일로 저장
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run(args.input, args.output)