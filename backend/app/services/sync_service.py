from datetime import datetime
from app.core.gcp_clients import db, get_drive_service
from app.models.file import FileSchema

def sync_file_metadata(file_id: str):
    service = get_drive_service()
    
    try:
        # 1. 구글 드라이브에서 파일 정보 조회 (UI에 필요한 필드 지정 필수)
        # fields 파라미터로 필요한 정보만 쏙쏙 골라옵니다 (성능 최적화)
        file_metadata = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, parents, thumbnailLink, iconLink, owners, createdTime, modifiedTime, trashed, webViewLink"
        ).execute()

        # 파일이 삭제(휴지통)된 경우 처리
        if file_metadata.get('trashed'):
            # TODO: 실제 삭제 정책에 따라 delete()를 할지 status update를 할지 결정 필요.
            # 현재는 soft delete 방식 유지.
            db.collection('files').document(file_id).update({'status': 'deleted'})
            print(f"File {file_id} marked as deleted.")
            return

        # 2. 데이터 가공 (Firestore 저장용)
        # 날짜 문자열을 파이썬 datetime 객체로 변환
        created_time_str = file_metadata.get('createdTime')
        created_dt = datetime.fromisoformat(created_time_str.replace('Z', '+00:00')) if created_time_str else datetime.now()

        modified_time_str = file_metadata.get('modifiedTime')
        modified_dt = datetime.fromisoformat(modified_time_str.replace('Z', '+00:00')) if modified_time_str else datetime.now()

        # Pydantic 모델 인스턴스 생성 (Data Validation)
        # app/models/file.py 에 있는 FileSchema 참조
        file_obj = FileSchema(
            file_id=file_metadata.get('id'),
            name=file_metadata.get('name'),
            mime_type=file_metadata.get('mimeType'),
            parents=file_metadata.get('parents', []),
            webview_link=file_metadata.get('webViewLink'),
            thumbnail_link=file_metadata.get('thumbnailLink'),
            icon_link=file_metadata.get('iconLink'),
            owners=[owner.get('displayName') for owner in file_metadata.get('owners', [])],
            is_folder=(file_metadata.get('mimeType') == 'application/vnd.google-apps.folder'),
            trashed=file_metadata.get('trashed', False),
            created_at=created_dt,
            updated_at=modified_dt,
            last_synced_at=datetime.now(),
            status='pending'  # 기본값 설정
        )

        # 3. Firestore에 저장 (Set with merge=True)
        db.collection('files').document(file_id).set(file_obj.model_dump(), merge=True) # -> 주소를 file_id로 지정해서 저장함!
        print(f"Successfully synced metadata for: {file_obj.name}")
        
        return file_obj # Pydantic 객체 반환 (타입 안전성 확보)

    except Exception as e:
        print(f"Error syncing metadata for {file_id}: {str(e)}")
        # raise e # Production에서는 에러 로깅 후 넘어갈지, 재시도 할지 결정 필요
        raise e
