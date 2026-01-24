from google.cloud import storage
import time
import datetime
import sys

# 설정
PROJECT_ID = "jnu-rise-edu-147"
GCS_INPUT_URI = "gs://omnihub-accounting-docs/Omnihub_Data/"
GCS_OUTPUT_URI = "gs://omnihub-accounting-docs/DocAI_Result/"

def count_blobs(bucket_name, prefix):
    """지정된 버킷과 prefix 경로의 파일 개수를 셉니다."""
    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(bucket_name)
        # blobs는 iterator이므로 리스트로 변환하지 않고 개수만 셉니다 (메모리 절약)
        return sum(1 for _ in bucket.list_blobs(prefix=prefix))
    except Exception as e:
        print(f"\n[오류] GCS 접속 실패: {e}")
        return 0

def parse_gs_uri(uri):
    if not uri.startswith("gs://"):
        return None, None
    parts = uri[5:].split("/", 1)
    bucket_name = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket_name, prefix

def main():
    print(f"[*] Document AI 모니터링을 시작합니다. (종료하려면 Ctrl+C)")
    print(f"[*] 5분마다 갱신됩니다...\n")

    in_bucket, in_prefix = parse_gs_uri(GCS_INPUT_URI)
    out_bucket, out_prefix = parse_gs_uri(GCS_OUTPUT_URI)
    
    # 1. 입력 파일 수 확인 (최초 1회)
    print(" - 입력 파일 수 계산 중...")
    total_input = count_blobs(in_bucket, in_prefix)
    print(f" - 총 입력 파일(PDF): {total_input}개")
    
    last_count = 0
    start_time = time.time()
    
    while True:
        try:
            # 출력 파일 수 확인
            current_count = count_blobs(out_bucket, out_prefix)
            now = datetime.datetime.now().strftime("%H:%M:%S")
            
            # 진행률 계산 (단순 파일 개수 비)
            percent = (current_count / total_input * 100) if total_input > 0 else 0
            
            # 증가량 확인
            delta = current_count - last_count
            if last_count == 0:
                delta_str = ""
            elif delta > 0:
                delta_str = f"(+{delta}개 증가)"
            else:
                delta_str = "(변동 없음)"

            # 상태 출력
            print(f"[{now}] 완료된 파일: {current_count}개 {delta_str} | 진행률: 약 {percent:.1f}%")
            
            # 완료 체크 (출력 파일은 입력 파일보다 많거나 같을 수 있음)
            if current_count >= total_input and delta == 0 and last_count != 0:
                print("\n[알림] 입력 파일 수만큼 처리가 완료된 것 같습니다!")
                print("       (Document AI는 페이지가 많으면 JSON이 쪼개지므로 100%를 넘을 수도 있습니다)")
                # 여기서 바로 종료하진 않고 사용자가 판단하도록 둠
                
            last_count = current_count
            
            # 300초(5분) 대기
            for _ in range(300):
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n모니터링을 종료합니다.")
            break
        except Exception as e:
            print(f"에러 발생: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
