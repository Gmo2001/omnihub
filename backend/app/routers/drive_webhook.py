from fastapi import APIRouter, Request, Header, BackgroundTasks
from app.services.sync_service import sync_file_metadata
from app.services.ingestion_service import process_and_catalog_file
from app.core.gcp_clients import get_drive_service, db
from app.services.drive_service import get_user_drive_service, stream_file_to_gcs
from app.models.user import UserSchema
from app.models.file import FileSchema
from app.schemas.ai_request import AIAnalysisRequest
import datetime
from typing import Optional
from app.core.logger import log_system_event
from app.utils.id_utils import to_internal_id # Added import

router = APIRouter()

# Firestore에서 마지막 동기화 토큰 관리 (서버 재시작시에도 유지되도록)
# [수정됨] 토큰 저장은 이제 사용자별로 동적으로 관리됩니다.

def get_page_token(user_email: str = "global"):
    doc_id = f'drive_sync_token_{user_email}'
    doc = db.collection('system').document(doc_id).get()
    if doc.exists:
        return doc.to_dict().get('token')
    return None

def save_page_token(token: str, user_email: str = "global"):
    doc_id = f'drive_sync_token_{user_email}'
    db.collection('system').document(doc_id).set({'token': token, 'updated_at': datetime.datetime.now()}, merge=True)

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
    [Real-time] 변경된 파일만 즉시 처리합니다.
    [Privacy] Whitelist(monitored_folder_ids)에 포함된 폴더의 파일만 처리합니다.
    """
    print(f"[Webhook] Resource State: {x_goog_resource_state}, Channel ID: {x_goog_channel_id}")

    # 1. Sync 알림
    if x_goog_resource_state == "sync":
        print(f"Channel {x_goog_channel_id} synced successfully.")
        return {"status": "ok"}

    # 2. 변경 알림
    if x_goog_resource_state in ["add", "update", "trash", "change"]:
        # 2-1. 채널 ID로 유저 식별
        channels = db.collection('watch_channels').where('channel_id', '==', x_goog_channel_id).stream()
        channel_doc = next(channels, None)
        
        if not channel_doc:
            print(f"[Webhook] Unknown Channel ID: {x_goog_channel_id}. Ignoring.")
            return {"status": "unknown_channel"}
            
        channel_data = channel_doc.to_dict()
        user_email = channel_data.get('user_email')
        
        # 유저 객체 복원
        user_ref = db.collection('users').document(user_email)
        user_snap = user_ref.get()
        if not user_snap.exists:
            return {"status": "user_not_found"}
            
        user = UserSchema(**user_snap.to_dict())
        monitored_ids = user.monitored_folder_ids # [Privacy] Whitelist
        
        # 2-2. Start Page Token 가져오기
        saved_token = get_page_token(user_email)
        
        try:
            drive_service = get_user_drive_service(user)
            
            # 2-3. 변경사항 조회
            response = drive_service.changes().list(
                pageToken=saved_token,
                fields="newStartPageToken, nextPageToken, changes(fileId, removed, file(id, name, mimeType, modifiedTime, trashed, parents))",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            changes = response.get('changes', [])
            new_token = response.get('newStartPageToken')
            
            print(f"[Webhook] Detected {len(changes)} changes for {user_email}.")
            
            for change in changes:
                file_id = change.get('fileId')
                file_item = change.get('file')
                
                # [Privacy Guard] Whitelist Check
                # monitored_ids가 비어있으면(초기 상태) 일단 다 허용하거나, 다 막아야 함.
                # 정책: "비어있으면 모든 파일 허용" vs "비어있으면 아무것도 안 함".
                # 사용자가 편의를 위해 "비어있으면 허용"으로 가되, 하나라도 있으면 필터링.
                if monitored_ids and file_item:
                    is_allowed = False
                    
                    # A. 직계 부모 확인
                    file_parents = file_item.get('parents', [])
                    if any(pid in monitored_ids for pid in file_parents):
                        is_allowed = True
                    
                    # B. 조상 추적 (Ancestry Check) - Max 5 levels
                    if not is_allowed and file_parents:
                        current_pid = file_parents[0] 
                        for _ in range(5):
                            if current_pid in monitored_ids:
                                is_allowed = True
                                break
                            try:
                                # 부모의 부모 조회 (Cache 권장되지만, 빈도가 낮으므로 직접 호출)
                                p_meta = drive_service.files().get(
                                    fileId=current_pid, fields="parents"
                                ).execute()
                                p_parents = p_meta.get('parents')
                                if not p_parents: break
                                current_pid = p_parents[0]
                            except:
                                break
                    
                    if not is_allowed:
                        print(f"[Privacy] Blocked {file_id}: Not in monitored folders.")
                        continue # Skip this file

                # A. 파일 삭제
                if change.get('removed') or (file_item and file_item.get('trashed')):
                    print(f"[Webhook] File removed/trashed: {file_id}")
                    auth_fil_id = to_internal_id('fil_', file_id)
                    
                    # 1. Update File Status (State Sync)
                    db.collection('files').document(auth_fil_id).update({
                        "trashed": True, 
                        "status": "deleted",
                        "updatedAt": datetime.datetime.now()
                    })
                    
                    # 2. Log Action (Audit Trail) - [Added]
                    action_type = ActionType.DELETE if change.get('removed') else ActionType.TRASH
                    
                    # 로그를 남기기 위해선 User 정보가 필요 (user 객체는 상단에서 이미 로드됨)
                    from app.services.log_service import log_user_action
                    from app.models.log import ActionType
                    
                    log_user_action(
                        user=user,
                        action=action_type,
                        file_id=file_id,
                        success=True,
                        details={
                            "method": "webhook_event",
                            "explicit_removal": change.get('removed', False)
                        }
                    )
                    continue
                
                # B. 파일 추가/수정
                if file_item:
                    print(f"[Webhook] Processing change: {file_item.get('name')} ({file_id})")
                    from app.services.ingestion_service import process_and_catalog_file
                    
                    background_tasks.add_task(
                        process_and_catalog_file,
                        user=user,
                        file_id=file_id,
                        drive_meta=file_item
                    )

            # 2-4. 새로운 Page Token 저장
            if new_token:
                save_page_token(new_token, user_email)
                
        except Exception as e:
            print(f"[Webhook] Error processing changes: {e}")
            
    return {"status": "processed"}

async def process_drive_changes(channel_id: Optional[str] = None):
    """
    변경된 파일 목록을 조회하고 파이프라인(Sync -> Ingestion)을 실행합니다.
    channel_id를 통해 User를 식별하여, 그 유저의 권한으로 조회합니다.
    """
    print(f"[Debug] process_drive_changes 시작. 받은 Channel ID: {channel_id}")
    drive_service = None
    user_email = "global"
    
    # 1. 사용자 식별 (Auto-Watch 지원)
    if channel_id:
        print(f"채널 ID 해결 중: {channel_id}")
        channel_doc = db.collection('watch_channels').document(channel_id).get()
        if channel_doc.exists:
            channel_data = channel_doc.to_dict()
            tgt_email = channel_data.get('user_email')
            
            # 사용자의 토큰 가져오기
            user_ref = db.collection('users').document(tgt_email).get()
            if user_ref.exists:
                user_obj = UserSchema(**user_ref.to_dict())
                try:
                    drive_service = get_user_drive_service(user_obj)
                    user_email = tgt_email
                    print(f"사용자로 처리 중: {user_email}")
                except Exception as e:
                    print(f"사용자 Drive 서비스 생성 실패: {e}")
        else:
            print("DB에서 채널 ID를 찾을 수 없습니다. 기본 서비스 계정으로 폴백합니다.")

    # 사용자를 찾지 못한 경우 서비스 계정 사용 (Fallback)
    if not drive_service:
        print("전역 서비스 계정을 사용하여 드라이브 접근.")
        drive_service = get_drive_service()
    
    # 2. 마지막 토큰 가져오기 (사용자별 분리)
    page_token = get_page_token(user_email)
    
    # 토큰이 없으면 최신 상태부터 시작 
    if not page_token:
         try:
             response = drive_service.changes().getStartPageToken().execute()
             page_token = response.get('startPageToken')
             print(f"새 StartPageToken 초기화 ({user_email}): {page_token}")
             save_page_token(page_token, user_email) # 초기 토큰 저장
         except Exception as e:
             print(f"StartPageToken 획득 실패: {e}")
             return

    # 3. 변경사항 리스트 조회 (Pagination)
    while page_token:
        try:
            results = drive_service.changes().list(
                pageToken=page_token,
                spaces='drive',
                # includeRemoved=True # 삭제된 파일도 추적하려면 필요 (기본값 True)
            ).execute()
        except Exception as e:
            print(f"변경사항 조회 실패 ({user_email}): {e}")
            break
            
        changes = results.get('changes', [])
        
        for change in changes:
            file_id = change.get('fileId')
            # [Phase 4] System Log: File Detected
            log_system_event(
                event_type="FILE_DETECTED",
                component="DriveWebhook",
                payload={"file_id": file_id, "user_email": user_email}
            )
            
            # 파이프라인 실행
            try:
                # 단계 1: 메타데이터 동기화 (DB 저장)
                # 경고: sync_file_metadata가 서비스 계정 권한만 사용하면 실패할 수 있었습니다.
                # Auto-Watch 구현을 위해 drive_service 객체를 전달받도록 수정했습니다.
                # 사용자 중심 로직이므로 서비스 계정 초대가 필요 없습니다.
                
                # 임시 수정: sync_file_metadata 로직을 덮어쓰거나 래핑?
                # 더 나은 방법: `drive_service`를 `sync_file_metadata`에 전달
                # 다음 단계에서 sync_service를 확인해야 함.
                # 일단 흐름을 유지하되, 위험 요소를 인지.
                
                file_obj: FileSchema = sync_file_metadata(file_id, drive_service=drive_service) 
                
                # 단계 2: 콘텐츠 추출 (내용 로드) -> AI 분석 대상인 경우
                # 폴더가 아니고, 삭제되지 않았을 때만 내용 추출
                if file_obj and not file_obj.is_folder and not file_obj.trashed:
                    # [Phase 3] 원본 파일 GCS 스트리밍 저장 (for Document AI / Gemini)
                    try:
                        gcs_result = stream_file_to_gcs(user_obj, file_id)
                        gcs_uri = gcs_result.get('gcs_uri')
                        
                        # DB에 GCS URI 업데이트
                        db.collection('files').document(file_id).update({"gcsUri": gcs_uri})
                        print(f"GCS 스트리밍 완료 ({file_obj.name}): {gcs_uri}")
                        
                        # 파일 객체에도 업데이트 (AI에게 전달용)
                        file_obj.gcs_uri = gcs_uri
                        
                    except Exception as gcs_error:
                        log_system_event(
                            event_type="GCS_UPLOAD_FAILED",
                            component="DriveWebhook",
                            payload={"file_id": file_id, "error": str(gcs_error)},
                            severity="ERROR"
                        )

                            print(f"AI 분석 의뢰 완료 (ID: {file_id})")

            except Exception as e:
                print(f"파일 처리 실패 {file_id}: {e}")
                # 에러 발생 시 상태 업데이트
                db.collection('files').document(file_id).set({"aiStatus": "failed", "errorMsg": str(e)}, merge=True)

        if 'newStartPageToken' in results:
            # 더 이상 변경사항이 없으면 newStartPageToken을 저장하고 종료
            save_page_token(results.get('newStartPageToken'), user_email)
            break
        
        # 다음 페이지가 있으면 계속 조회
        page_token = results.get('nextPageToken')
        save_page_token(page_token, user_email) # 중간 저장

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
