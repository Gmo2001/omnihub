import io
from typing import Dict, Any
import pypdf
from PIL import Image

def extract_internal_metadata(file_content: bytes, mime_type: str) -> Dict[str, Any]:
    metadata = {}
    
    try:
        # 1. PDF 분석
        if mime_type == 'application/pdf':
            try:
                pdf_file = io.BytesIO(file_content)
                reader = pypdf.PdfReader(pdf_file)
                pdf_meta = reader.metadata
                
                if pdf_meta:
                    # [수정] 정해진 키만 가져오는 게 아니라, 모든 키를 다 가져옵니다.
                    for key, value in pdf_meta.items():
                        # PDF 메타데이터 키는 보통 '/KeyName' 형식이므로 앞의 '/'를 제거
                        clean_key = key.replace('/', '') if key.startswith('/') else key
                        
                        # 값이 있으면 저장 (문자열로 변환)
                        if value:
                            # 리스트 형태의 문자열(예: "['tag1', 'tag2']")이 들어올 수도 있으니
                            # 필요하다면 여기서 파싱 로직을 추가할 수도 있습니다.
                            metadata[clean_key] = str(value)
                            
                # [추가] XMP 메타데이터도 확인 (Adobe 제품군 등에서 주입한 경우 여기에 있을 수 있음)
                try:
                    xmp = reader.xmp_metadata
                    if xmp:
                        # XMP 데이터 중 custom_properties가 있다면 병합
                        # (단순화를 위해 여기서는 XML 전체를 뒤지지 않고 기본 메타만 우선 처리)
                        pass
                except:
                    pass
                            
            except Exception as e:
                print(f"[Metadata] PDF decoding failed: {e}")

        # 2. 이미지 분석 (EXIF) - 기존 유지
        elif mime_type.startswith('image/'):
            try:
                image_file = io.BytesIO(file_content)
                with Image.open(image_file) as img:
                    exif_data = img._getexif()
                    if exif_data:
                        from PIL.ExifTags import TAGS
                        for tag_id, value in exif_data.items():
                            tag_name = TAGS.get(tag_id, tag_id)
                            # 너무 긴 바이너리 데이터 제외
                            if tag_name not in ['MakerNote', 'UserComment'] and not isinstance(value, bytes):
                                metadata[str(tag_name)] = str(value)
            except Exception as e:
                print(f"[Metadata] Image decoding failed: {e}")

    except Exception as e:
        print(f"[Metadata] Critical error during extraction: {e}")
        return {}
        
    return metadata