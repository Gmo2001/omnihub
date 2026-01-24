from google.cloud import storage
import time

# 설정 (기본 스크립트와 동일)
PROJECT_ID = "jnu-rise-edu-147"
GCS_INPUT_URI = "gs://omnihub-accounting-docs/Omnihub_Data/"
GCS_OUTPUT_URI = "gs://omnihub-accounting-docs/DocAI_Result/"

def count_blobs(bucket_name, prefix):
    """지정된 버킷과 prefix 경로의 파일 개수를 셉니다."""
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    return len(blobs)

def parse_gs_uri(uri):
    if not uri.startswith("gs://"):
        return None, None
    parts = uri[5:].split("/", 1)
    bucket_name = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket_name, prefix

def main():
    print("[*] Document AI 진행 상황 확인 중...")
    
    # 1. 입력 파일 수 확인
    in_bucket, in_prefix = parse_gs_uri(GCS_INPUT_URI)
    total_files = count_blobs(in_bucket, in_prefix)
    print(f" - 입력 파일(PDF 등) 개수: {total_files}개")

    # 2. 출력 파일 수 확인
    out_bucket, out_prefix = parse_gs_uri(GCS_OUTPUT_URI)
    processed_files = count_blobs(out_bucket, out_prefix)
    
    # Document AI는 결과당 폴더/파일이 여러 개 생길 수 있으므로 단순 개수 비교는 대략적입니다.
    # 보통 입력 파일 1개당 출력 JSON파일이 최소 1개 이상 생성됩니다.
    print(f" - 출력 파일(JSON) 개수:   {processed_files}개 (생성된 결과 파일 수)")
    
    if total_files > 0:
        print(f"\n[참고] 출력 파일이 늘어나고 있다면 정상적으로 진행 중인 것입니다.")
    else:
        print("[주의] 입력 경로에 파일이 없습니다.")

if __name__ == "__main__":
    main()
