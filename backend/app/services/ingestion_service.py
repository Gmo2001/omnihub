from app.core.gcp_clients import get_drive_service
import io
from googleapiclient.http import MediaIoBaseDownload

def ingest_file_content(file_id: str, mime_type: str) -> str:
    """
    Google Drive 파일의 내용을 텍스트로 추출합니다.
    - Google Docs/Sheets/Slides: text/plain으로 변환(Export)하여 다운로드
    - 일반 텍스트/PDF: 바이너리 다운로드 (현재는 텍스트 파일 단순 디코딩 예시)
    """
    service = get_drive_service()
    content = ""
    
    try:
        # 1. Google Workspace 문서 (Docs, Sheets, Slides) -> Text Export
        if mime_type.startswith("application/vnd.google-apps"):
            if "folder" in mime_type:
                return "" # 폴더는 내용 없음
            
            # export() 사용: 구글 전용 포맷을 일반 텍스트로 변환
            # Sheets는 csv, Slides는 plain text 등으로 변환됨
            response = service.files().export(
                fileId=file_id, 
                mimeType='text/plain'
            ).execute()
            
            # export 결과는 bytes 형태이므로 디코딩
            content = response.decode('utf-8')
            print(f"[Ingestion] Exported Google Doc {file_id} (len: {len(content)})")
            
        # 2. 일반 파일 (txt, md, csv 등) -> Binary Download
        # PDF의 경우 별도의 OCR/PDF 파서(PyPDF2, PDFPlumber 등)가 필요하므로
        # 여기서는 단순 텍스트 기반 파일만 처리한다고 가정합니다.
        else:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # 다운로드 완료 후 포인터 리셋
            fh.seek(0)
            
            # 텍스트 파일로 가정하고 디코딩 시도 (바이너리 파일은 에러날 수 있음)
            try:
                content = fh.read().decode('utf-8')
                print(f"[Ingestion] Downloaded File {file_id} (len: {len(content)})")
            except UnicodeDecodeError:
                content = f"[Binary Content] Mime-Type: {mime_type} (Non-text file)"
                print(f"[Ingestion] Binary file detected: {file_id}")

        return content

    except Exception as e:
        print(f"Error extracting content for {file_id}: {str(e)}")
        # 에러 발생 시 None 대신 빈 문자열 반환하거나 에러를 상위로 전파
        return ""
