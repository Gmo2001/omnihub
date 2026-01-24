import re
from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.cloud import storage

# =============================================================================
# [사용자 설정] ★여기를 수정하세요★
# =============================================================================
PROJECT_ID = "jnu-rise-edu-147"               # 본인 프로젝트 ID
LOCATION = "us"                               # 프로세서 만든 위치 (US)
PROCESSOR_ID = "959c67487af7cfff" # 예: "90e66f87b896e54"
GCS_INPUT_URI = "gs://omnihub-accounting-docs/Omnihub_Data/" # PDF 들어있는 곳
GCS_OUTPUT_URI = "gs://omnihub-accounting-docs/DocAI_Result/" # JSON 결과 저장할 곳

# =============================================================================
# Document AI 배치 처리 함수
# =============================================================================
def batch_process_documents(
    project_id: str,
    location: str,
    processor_id: str,
    gcs_input_uri: str,
    gcs_output_uri: str,
    timeout: int = 4000  # 대기 시간 (초)
):
    # 1. 클라이언트 설정 (US 리전 엔드포인트)
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    # 2. 리소스 이름 구성
    processor_name = client.processor_path(project_id, location, processor_id)

    # 3. 입력 설정 (GCS의 모든 PDF 파일)
    # 주의: Document AI는 폴더 단위 입력을 위해 GcsPrefix를 사용합니다.
    input_config = documentai.BatchDocumentsInputConfig(
        gcs_prefix=documentai.GcsPrefix(gcs_uri_prefix=gcs_input_uri)
    )

    # 4. 출력 설정 (GCS에 JSON으로 저장)
    output_config = documentai.DocumentOutputConfig(
        gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
            gcs_uri=gcs_output_uri
        )
    )

    # 5. 요청 생성 및 전송
    request = documentai.BatchProcessRequest(
        name=processor_name,
        input_documents=input_config,
        document_output_config=output_config,
    )

    print(f"[*] Document AI 배치 작업을 시작합니다...")
    print(f" - 입력: {gcs_input_uri}")
    print(f" - 출력: {gcs_output_uri}")
    print(f" - 프로세서: {processor_id}")
    
    # LRO (Long Running Operation) 시작
    operation = client.batch_process_documents(request)
    print(f"[*] Operation ID: {operation.operation.name}")

    print(f"[*] 작업이 서버로 전송되었습니다. 10분 동안 대기 후 스크립트는 종료됩니다.")
    print(f"    (서버에서의 작업은 계속 진행되니 안심하세요. 모니터링은 monitor_docai.py를 이용하세요)")
    
    # 결과 대기 (10분 설정)
    try:
        # 600초(10분) 동안만 대기
        operation.result(timeout=600)
        print("[완료] 모든 문서 변환이 10분 내에 끝났습니다!")
    except Exception as e:
        # 10분이 지나면 Timeout 에러가 발생하지만, 이는 의도된 동작입니다.
        print(f"\n[알림] 10분이 지났습니다. 스크립트를 종료합니다.")
        print(f"       서버에서 작업({operation.operation.name})은 계속 진행 중입니다.")
        print(f"       'monitor_docai.py'를 실행하여 진행 상황을 확인하세요.")

if __name__ == "__main__":
    # 프로세서 ID가 입력되었는지 확인
    if "여기에" in PROCESSOR_ID:
        print("[오류] PROCESSOR_ID를 설정해주세요.")
    else:
        batch_process_documents(
            PROJECT_ID,
            LOCATION,
            PROCESSOR_ID,
            GCS_INPUT_URI,
            GCS_OUTPUT_URI
        )