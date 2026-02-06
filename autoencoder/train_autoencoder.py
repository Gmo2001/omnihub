# src/autoencoder/train_autoencoder.py
from xml.parsers.expat import model
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

if __name__ == "__main__":
    main()
