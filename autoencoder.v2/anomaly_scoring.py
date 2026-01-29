import argparse
import json
import numpy as np
import joblib
import pandas as pd
from tensorflow import keras
from .config import MODEL_PATH, SCALER_PATH, BASELINE_PATH


WATCH_THRESHOLD = 2.0
ALERT_THRESHOLD = 3.0

def load_artifacts():
    model = keras.models.load_model(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(BASELINE_PATH, "r") as f:
        baseline = json.load(f)
    return model, scaler, baseline

def compute_recon_error(model, X_scaled):
    X_pred = model.predict(X_scaled)
    return np.mean((X_scaled - X_pred) ** 2, axis=1)

def score_batch(model, scaler, baseline, X_raw):
    X_scaled = scaler.transform(X_raw)
    recon_err = compute_recon_error(model, X_scaled)

    mean = baseline["train_mean"]
    std = baseline["train_std"]
    z = (recon_err - mean) / (std + 1e-8)

    level = np.where(
        z >= ALERT_THRESHOLD, "ALERT",
        np.where(z >= WATCH_THRESHOLD, "WATCH", "NORMAL")
    )

    return {
        "recon_error": recon_err,
        "z_score": z,
        "level": level,
    }

def run(input_path: str, output_path: str):
    # 1) CSV 읽기
    df = pd.read_csv(input_path)

    # 2) 모델 / 스케일러 / 기준값 불러오기
    model = keras.models.load_model(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(BASELINE_PATH, "r") as f:
        baseline = json.load(f)
    threshold = baseline["p95"]


    # 3) 피처 선택 (빅쿼리 CSV 기준으로 숫자 컬럼만)
    feature_cols = [
    "user_downloads_5m",
    "z_pos",
    ]   
    
    X = df[feature_cols]

    # 4) 스케일링
    X_scaled = scaler.transform(X)

    # 5) 재구성 오차 계산
    X_recon = model.predict(X_scaled)
    recon_error = ((X_scaled - X_recon) ** 2).mean(axis=1)

    # 6) 이상 여부 플래그
    df["recon_error"] = recon_error
    df["is_anomaly"] = (recon_error > threshold).astype(int)

    # 7) 결과 저장
    df.to_csv(output_path, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run(args.input, args.output)