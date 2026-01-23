from google.cloud import documentai
from google.api_core.client_options import ClientOptions
from app.core.config import settings
from typing import Optional, Dict, Any, List
import re
from datetime import datetime

# 1. 설정 로드 (Load Config) 
# .env -> config.py -> settings 순으로 로드된 값을 사용합니다.
LOCATION = settings.DOCAI_LOCATION
PROCESSOR_ID = settings.DOCAI_PROCESSOR_ID
PROJECT_ID = settings.PROJECT_ID

def get_client():
    opts = ClientOptions(api_endpoint=f"{LOCATION}-documentai.googleapis.com")
    return documentai.DocumentProcessorServiceClient(client_options=opts)

def process_documents_batch(
    items: List[Dict[str, str]] # [{"gcs_uri": "...", "mime_type": "..."}, ...]
) -> List[Dict[str, Any]]:
    """
    [배치 처리] 여러 GCS 파일들에 대해 Document AI 처리를 요청하고 결과를 반환합니다.
    각 파일별로 다른 MIME Type을 처리할 수 있도록 수정했습니다.
    """
    client = get_client()
    name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

    results = []

    # Online Request 루프 (프로토타입 및 소규모 파일용)
    for item in items:
        uri = item.get("gcs_uri")
        mime_type = item.get("mime_type", "application/pdf") # 개별 파일의 mime_type 사용
        
        try:
            gcs_document = documentai.GcsDocument(
                gcs_uri=uri,
                mime_type=mime_type
            )
            request = documentai.ProcessRequest(
                name=name,
                gcs_document=gcs_document,
                skip_human_review=True
            )
            # API 호출
            response = client.process_document(request=request)
            
            # 스키마 매핑
            doc_output = map_docai_proto_to_schema(response.document, uri, name)
            results.append(doc_output)
            
        except Exception as e:
            print(f"Error processing {uri}: {e}")
            # 에러 발생 시에도 빈 결과나 에러 로그 포함하여 계속 진행
            results.append({
                "doc_id": "error", 
                "source": {"original_gcs_uri": uri}, 
                "errors": [{"message": str(e)}]
            })

    return results

def map_docai_proto_to_schema(document: documentai.Document, gcs_uri: str, processor_name: str) -> Dict[str, Any]:
    """
    Document AI Proto 결과를 'docai_output.json' 스키마에 맞춰 변환
    """
    
    # 텍스트 추출 헬퍼
    def get_text(text_anchor):
        if not text_anchor.text_segments:
            return ""
        startIndex = text_anchor.text_segments[0].start_index
        endIndex = text_anchor.text_segments[0].end_index
        return document.text[startIndex:endIndex]

    # Pages 매핑
    pages_data = []
    for page in document.pages:
        page_obj = {
            "page_number": page.page_number,
            "text": "", # 전체 텍스트에서 해당 페이지 분량 추출 필요 (여기선 생략하거나 블록 텍스트 합침)
            "blocks": [],
            # "tables": [] # Optional
        }
        
        # Blocks (Paragraphs)
        page_text_buffer = []
        for block in page.blocks:
            block_text = get_text(block.layout.text_anchor)
            page_text_buffer.append(block_text)
            
            # Bounding Box (Normalized)
            vertices = []
            if block.layout.bounding_poly.normalized_vertices:
                vertices = [{"x": v.x, "y": v.y} for v in block.layout.bounding_poly.normalized_vertices]
            
            block_obj = {
                "block_id": f"p{page.page_number}_b{len(page_obj['blocks'])}", # 임의 ID 생성
                "type": "paragraph", 
                "text": block_text,
                "bbox": {
                    "normalized_vertices": vertices
                },
                "confidence": block.layout.confidence
            }
            page_obj["blocks"].append(block_obj)
            
        page_obj["text"] = "\n".join(page_text_buffer)
        pages_data.append(page_obj)

    # docai_output.json 스키마 준수
    output = {
        "doc_id": f"doc_{str(gcs_uri).split('/')[-1]}", # 간단한 ID 생성 (파일명 활용)
        "source": {
            "drive_file_id": "unknown", # 호출처(ingest)에서 주입 필요
            "drive_revision_id": "unknown",
            "mime_type": document.mime_type,
            "original_gcs_uri": gcs_uri
        },
        "docai": {
            "processor_name": processor_name,
            "processor_version": "v1", # 응답 헤더 등에서 가져올 수 있으나 보통 고정
            "processed_at": datetime.utcnow().isoformat()
        },
        "pages": pages_data
    }
    
    return output
