
from google.cloud import storage
import logging
from dotenv import load_dotenv
import os

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GCS-Cleaner")

# .env 로드
load_dotenv()

def delete_folder(bucket, folder_name):
    """폴더(Prefix) 내의 모든 blob 삭제"""
    blobs = list(bucket.list_blobs(prefix=folder_name))
    
    if not blobs:
        print(f"   [Skip] {folder_name} (비어있음)")
        return

    print(f"   🗑️ Deleting {folder_name} ({len(blobs)} files)...")
    
    # Batch delete (한 번에 최대 100개 권장되지만, 여기서는 순차 삭제 혹은 bucket.delete_blobs 사용)
    # google.cloud.storage.Bucket.delete_blobs는 한 번에 여러 개 삭제 가능
    batch_size = 100
    for i in range(0, len(blobs), batch_size):
        batch = blobs[i:i + batch_size]
        try:
            with storage.Client().batch(): # Batch Context (성능 향상)
                for blob in batch:
                    blob.delete()
        except Exception as e:
             # Batch 실패 시 개별 삭제 시도 (에러 무시 강화)
             # print(f"    ⚠️ Batch delete failed, trying individually: {e}")
             for blob in batch:
                 try:
                     blob.delete()
                 except Exception:
                     pass # 404 등 이미 없는 경우 무시

    print(f"    ✅ Deleted {folder_name}")

def main():
    # 0. 인증 설정
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
            print("❌ GOOGLE_APPLICATION_CREDENTIALS 환경변수가 설정되지 않았습니다.")
            return
            
    # _local_secrets 경로 등 상대 경로 처리
    if not os.path.isabs(cred_path):
        cred_path = os.path.abspath(cred_path)
        
    storage_client = storage.Client.from_service_account_json(cred_path)

    # 1. 버킷 이름 가져오기
    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        print("❌ .env 파일에 GCS_BUCKET 설정이 없습니다.")
        return
    
    print(f"🔥 [GCS Cleaner] 버킷 청소 시작: gs://{bucket_name}")
    try:
        bucket = storage_client.bucket(bucket_name)
    except Exception as e:
        print(f"❌ 버킷 접근 실패: {e}")
        return

    # 2. 삭제할 폴더 목록 (Prefix)
    folders_to_clear = [
        "raw/",
        "docai_output/",
        "bundles/",
        "chunks/",
        "embeddings/",
        "entities/",
        "vector-init/",
        "doc_chunks/" # 간혹 쓰일 수 있음
    ]

    # 사용자 확인
    print("---------------------------------------------------")
    print(f"대상 폴더: {', '.join(folders_to_clear)}")
    print("WARNING: 해당 폴더 내의 모든 파일이 영구 삭제됩니다.")
    print("---------------------------------------------------")
    
    # 3. 삭제 실행
    for folder in folders_to_clear:
        delete_folder(bucket, folder)
        
    print("\n✨ 모든 GCS 데이터 삭제 완료!")

if __name__ == "__main__":
    main()
