import functions_framework
import traceback
from google.cloud import storage
import pandas as pd
import io
import joblib
import json
import datetime
import numpy as np
from tensorflow import keras

@functions_framework.cloud_event
def score_new_csv(cloud_event):
    data = cloud_event.data
    bucket_name = data['bucket']
    file_path = data['name']

    # 1. 입력 파일 필터링: inputs/ 폴더의 csv만 처리
    if not file_path.startswith('inputs/') or not file_path.endswith('.csv'):
        return 'OK'

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    try:
        # 2. 모델 파일 다운로드 (안전하게 매번 다운로드)
        for mf in ['autoencoder.keras', 'scaler.pkl', 'baseline.json']:
            blob = bucket.blob(f'models/{mf}')
            blob.download_to_filename(f'/tmp/{mf}')
        
        # 모델 로드
        model = keras.models.load_model('/tmp/autoencoder.keras')
        scaler = joblib.load('/tmp/scaler.pkl')
        with open('/tmp/baseline.json') as f:
            threshold_data = json.load(f)
            threshold = threshold_data['threshold']

        # 3. CSV 데이터 읽기
        blob = bucket.blob(file_path)
        content = blob.download_as_text()
        df = pd.read_csv(io.StringIO(content))
        
        # 4. 전처리 및 예측 (숫자 컬럼만 사용)
        feature_cols = ['userDownloads5m', 'zPos']
        X = df[feature_cols].values
        X_scaled = scaler.transform(X)
        
        # 오토인코더 예측 및 재구성 오차(MSE) 계산
        preds = model.predict(X_scaled)
        mse = np.mean(np.power(X_scaled - preds, 2), axis=1)

        # 5. 결과 JSON 생성 (요청하신 형식 준수)
        results = []
        
        # 스케일러 정보 추출 (없으면 기본값)
        train_mean = float(np.mean(scaler.mean_)) if hasattr(scaler, 'mean_') else 0.0
        train_std = float(np.mean(scaler.scale_)) if hasattr(scaler, 'scale_') else 1.0

        for i in range(len(df)):
            row = df.iloc[i]
            score = float(mse[i])
            
            # 한 줄씩 딕셔너리로 변환
            record = {
                "traceId": str(row.get('traceId', f'unknown_{i}')),
                "windowStart": str(row.get('windowStart', datetime.datetime.utcnow().isoformat())),
                "userId": str(row.get('userId', 'unknown')),
                "eventType": int(row.get('eventType', 0)),
                "trainMean": train_mean,
                "trainStd": train_std,
                "p95Threshold": float(threshold),
                "reconError": score,
                "metadata": {
                    "userDownloads5m": float(row.get('userDownloads5m', 0.0)),
                    "zPos": float(row.get('zPos', 0.0))
                }
            }
            results.append(record)

        # 6. JSON 파일로 저장 (outputs/ 폴더)
        # 예: inputs/data.csv -> outputs/data.json
        output_filename = file_path.replace('inputs/', 'outputs/').replace('.csv', '.json')
        output_blob = bucket.blob(output_filename)
        
        # JSON 문자열로 변환하여 업로드
        output_blob.upload_from_string(
            json.dumps(results, indent=2),
            content_type='application/json'
        )

        print(f"✅ Saved JSON to: gs://{bucket_name}/{output_filename}")

    except Exception as e:
        print(f"❌ Error processing {file_path}: {str(e)}")
        traceback.print_exc()
    return 'OK'
import functions_framework
import traceback
from google.cloud import storage
import pandas as pd
import io
import joblib
import json
import datetime
import numpy as np
from tensorflow import keras

@functions_framework.cloud_event
def score_new_csv(cloud_event):
    data = cloud_event.data
    bucket_name = data['bucket']
    file_path = data['name']

    # 1. 입력 파일 필터링: inputs/ 폴더의 csv만 처리
    if not file_path.startswith('inputs/') or not file_path.endswith('.csv'):
        return 'OK'

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    try:
        # 2. 모델 파일 다운로드 (안전하게 매번 다운로드)
        for mf in ['autoencoder.keras', 'scaler.pkl', 'baseline.json']:
            blob = bucket.blob(f'models/{mf}')
            blob.download_to_filename(f'/tmp/{mf}')
        
        # 모델 로드
        model = keras.models.load_model('/tmp/autoencoder.keras')
        scaler = joblib.load('/tmp/scaler.pkl')
        with open('/tmp/baseline.json') as f:
            threshold_data = json.load(f)
            threshold = threshold_data['threshold']

        # 3. CSV 데이터 읽기
        blob = bucket.blob(file_path)
        content = blob.download_as_text()
        df = pd.read_csv(io.StringIO(content))
        
        # 4. 전처리 및 예측 (숫자 컬럼만 사용)
        feature_cols = ['userDownloads5m', 'zPos']
        X = df[feature_cols].values
        X_scaled = scaler.transform(X)
        
        # 오토인코더 예측 및 재구성 오차(MSE) 계산
        preds = model.predict(X_scaled)
        mse = np.mean(np.power(X_scaled - preds, 2), axis=1)

        # 5. 결과 JSON 생성 (요청하신 형식 준수)
        results = []
        
        # 스케일러 정보 추출 (없으면 기본값)
        train_mean = float(np.mean(scaler.mean_)) if hasattr(scaler, 'mean_') else 0.0
        train_std = float(np.mean(scaler.scale_)) if hasattr(scaler, 'scale_') else 1.0

        for i in range(len(df)):
            row = df.iloc[i]
            score = float(mse[i])
            
            # 한 줄씩 딕셔너리로 변환
            record = {
                "traceId": str(row.get('traceId', f'unknown_{i}')),
                "windowStart": str(row.get('windowStart', datetime.datetime.utcnow().isoformat())),
                "userId": str(row.get('userId', 'unknown')),
                "eventType": int(row.get('eventType', 0)),
                "trainMean": train_mean,
                "trainStd": train_std,
                "p95Threshold": float(threshold),
                "reconError": score,
                "metadata": {
                    "userDownloads5m": float(row.get('userDownloads5m', 0.0)),
                    "zPos": float(row.get('zPos', 0.0))
                }
            }
            results.append(record)

        # 6. JSON 파일로 저장 (outputs/ 폴더)
        # 예: inputs/data.csv -> outputs/data.json
        output_filename = file_path.replace('inputs/', 'outputs/').replace('.csv', '.json')
        output_blob = bucket.blob(output_filename)
        
        # JSON 문자열로 변환하여 업로드
        output_blob.upload_from_string(
            json.dumps(results, indent=2),
            content_type='application/json'
        )

        print(f"Saved JSON to: gs://{bucket_name}/{output_filename}")

    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        traceback.print_exc()
    return 'OK'
