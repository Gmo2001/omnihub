from fastapi import APIRouter, Request, Header, BackgroundTasks
from app.services.sync_service import sync_file_metadata
from app.services.ingestion_service import ingest_file_content
from app.core.gcp_clients import get_drive_service, db
from app.models.file import FileSchema
import datetime

router = APIRouter()

# Firestore에서 마지막 동기화 토큰 관리 (서버 재시작시에도 유지되도록)
TOKEN_DOC_REF = db.collection('system').document('drive_sync_token')

def get_start_page_token():
    doc = TOKEN_DOC_REF.get()
    if doc.exists:
        return doc.to_dict().get('token')
    return None

def save_start_page_token(token: str):
    TOKEN_DOC_REF.set({'token': token, 'updated_at': datetime.datetime.now()}, merge=True)

@router.post("/webhook/drive")
async def handle_drive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_goog_resource_state: str = Header(None),
    x_goog_channel_id: str = Header(None),
    x_goog_resource_id: str = Header(None)
):
    """
    구글 드라이브로부터 변경 알림(Push Notification)을 수신하는 API입니다.
    """
    print(f"[Webhook] Resource State: {x_goog_resource_state}, Channel ID: {x_goog_channel_id}")

    # 1. Sync 알림 (채널 생성 시 최초 1회 발생, 또는 갱신 시)
    if x_goog_resource_state == "sync":
        print(f"Channel {x_goog_channel_id} synced successfully. Watching resource: {x_goog_resource_id}")
        return {"status": "ok"}

    # 2. 변경 알림 (Add, Update, Trash 등) - 실제 내용은 알려주지 않음
    if x_goog_resource_state in ["add", "update", "trash", "change"]:
        print("Change detected in Drive! Fetching changes...")
        
        # Webhook은 '뭔가 변했다'만 알려주므로, 실제 변경사항은 changes().list()로 조회해야 함
        # 백그라운드 태스크로 위임하여 Webhook 요청에 빠르게 응답 (구글 타임아웃 방지)
        background_tasks.add_task(process_drive_changes)

    return {"status": "processed"}

async def process_drive_changes():
    """
    변경된 파일 목록을 조회하고 파이프라인(Sync -> Ingestion)을 실행합니다.
    """
    service = get_drive_service()
    
    # 1. 마지막 토큰 가져오기
    page_token = get_start_page_token()
    
    # 토큰이 없으면 최신 상태부터 시작 (또는 처음부터 하려면 getStartPageToken() 사용 안하고 None으로 시작하면 되지만 너무 많을 수 있음)
    if not page_token:
         response = service.changes().getStartPageToken().execute()
         page_token = response.get('startPageToken')
         print(f"Initialized new startPageToken: {page_token}")

    # 2. 변경사항 리스트 조회 (Pagination)
    while page_token:
        try:
            results = service.changes().list(
                pageToken=page_token,
                spaces='drive',
                # includeRemoved=True # 삭제된 파일도 추적하려면 필요 (기본값 True)
            ).execute()
        except Exception as e:
            print(f"Error fetching changes: {e}")
            break
            
        changes = results.get('changes', [])
        
        for change in changes:
            file_id = change.get('fileId')
            print(f"Processing Change: File ID {file_id}")
            
            # 파이프라인 실행
            try:
                # Step 1: 메타데이터 동기화 (DB 저장)
                file_obj: FileSchema = sync_file_metadata(file_id)
                
                # Step 2: 콘텐츠 추출 (내용 로드) -> AI 분석 대상인 경우
                # 폴더가 아니고, 삭제되지 않았을 때만 내용 추출
                if file_obj and not file_obj.is_folder and not file_obj.trashed:
                    content = ingest_file_content(file_id, file_obj.mime_type)
                    
                    if content:
                        print(f"Content extracted for {file_obj.name}: {len(content)} chars")
                        
                        # Step 3: AI Agent에게 분석 요청
                        from app.services.ai_service import analyze_file_content
                        
                        # AI 상태 'processing'으로 업데이트
                        db.collection('files').document(file_id).update({"ai_status": "processing"})

                        ai_result = await analyze_file_content(content, file_obj)
                        
                        # Step 4: 분석 결과 DB 업데이트
                        if ai_result:
                            db.collection('files').document(file_id).set(ai_result, merge=True)
                            print(f"DB Updated with AI results for {file_id}")

            except Exception as e:
                print(f"Failed to process file {file_id}: {e}")
                # 에러 발생 시 상태 업데이트
                db.collection('files').document(file_id).set({"ai_status": "failed", "error_msg": str(e)}, merge=True)

        if 'newStartPageToken' in results:
            # 더 이상 변경사항이 없으면 newStartPageToken을 저장하고 종료
            save_start_page_token(results.get('newStartPageToken'))
            break
        
        # 다음 페이지가 있으면 계속 조회
        page_token = results.get('nextPageToken')
        save_start_page_token(page_token) # 중간 저장

# === Admin / Setup API ===
from pydantic import BaseModel
from app.utils.drive_watch import start_watching_drive

class WatchRequest(BaseModel):
    webhook_url: str

@router.post("/drive/watch")
async def enable_drive_watch(body: WatchRequest):
    """
    [Admin] 구글 드라이브 변경 알림(Watch)을 시작합니다.
    - Cloud Run 배포 후, 해당 서버의 Webhook URL을 등록해야 합니다.
    """
    try:
        result = start_watching_drive(webhook_url=body.webhook_url)
        return {"status": "success", "info": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
