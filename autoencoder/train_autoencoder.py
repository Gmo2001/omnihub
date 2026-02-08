# src/autoencoder/train_autoencoder.py
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from tensorflow import keras
from tensorflow.keras import layers
import json
import joblib

from config import INPUT_DIM, LATENT_DIM, MODEL_PATH, SCALER_PATH, BASELINE_PATH

def build_autoencoder(input_dim, latent_dim):
    encoder = keras.Sequential([
        layers.Dense(64, activation="relu", input_shape=(input_dim,)),
        layers.Dropout(0.2),
        layers.Dense(32, activation="relu"),
        layers.Dense(latent_dim, activation="relu"),
    ])
    decoder = keras.Sequential([
        layers.Dense(32, activation="relu", input_shape=(latent_dim,)),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.2),
        layers.Dense(input_dim, activation="sigmoid"),
    ])
    autoencoder = keras.Sequential([encoder, decoder])
    autoencoder.compile(optimizer="adam", loss="mse")
    return autoencoder

def fit_autoencoder(X: np.ndarray):
    """
    X: (n_samples, INPUT_DIM) numpy array (raw input)
    return: model, scaler, baseline_stats(dict)
    """
    # 1) 스케일링
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 2) train/val split
    X_train, X_val = train_test_split(X_scaled, test_size=0.2, random_state=42)

    # 3) 모델 생성 및 학습
    model = build_autoencoder(INPUT_DIM, LATENT_DIM)
    history = model.fit(
        X_train,
        X_train,
        epochs=50,
        batch_size=32,
        validation_data=(X_val, X_val),
        verbose=1,
    )

    # 4) 재구성 오차 기반 baseline 계산
    train_recon = model.predict(X_train)
    train_err = np.mean((X_train - train_recon) ** 2, axis=1)

    baseline = {
        "trainMean": float(train_err.mean()),
        "trainStd": float(train_err.std()),
        "p95Threshold": float(np.percentile(train_err, 95)),
    }

    return model, scaler, baseline

def save_artifacts(model, scaler, baseline: dict):
    model.save(MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    with open(BASELINE_PATH, "w") as f:
        json.dump(baseline, f)

def main():
    # TODO: 실제 데이터 로딩 부분은 여기서 호출
    # ex) BigQuery에서 당겨온 np.array를 여기로 넣기
    # 지금은 기존 노트북의 dummy data 로직을 그대로 복사해와도 됨
    n_samples = 1000
    normal_data = np.random.normal(0, 1, (n_samples, INPUT_DIM))
    anomaly_data = np.random.normal(5, 2, (50, INPUT_DIM))
    data = np.vstack([normal_data, anomaly_data])

    model, scaler, baseline = fit_autoencoder(data)
    save_artifacts(model, scaler, baseline)
    
    # GCS로 자동 업로드 (파이프라인 연동용 - 복구됨)
    upload_artifacts_to_gcs()

def upload_artifacts_to_gcs(bucket_name="aib-riskscore", source_dir="models", destination_blob_prefix="models"):
    """
    로컬 models/ 폴더의 파일들을 gs://aib-riskscore/models/ 로 업로드
    """
    try:
        from google.cloud import storage
        import os
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        if not os.path.exists(source_dir):
            print(f"[WARN] {source_dir} directory not found. Skipping upload.")
            return

        print(f"[UPLOAD] Starting upload from {source_dir} to gs://{bucket_name}/{destination_blob_prefix}...")
        for filename in os.listdir(source_dir):
            local_path = os.path.join(source_dir, filename)
            if os.path.isfile(local_path):
                blob_path = f"{destination_blob_prefix}/{filename}"
                blob = bucket.blob(blob_path)
                blob.upload_from_filename(local_path)
                print(f" - Uploaded {filename}")
        print("[SUCCESS] All model artifacts uploaded.")
    except Exception as e:
        print(f"[ERROR] Failed to upload to GCS: {e}")

if __name__ == "__main__":
    main()
