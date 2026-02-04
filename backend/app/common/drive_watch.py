import uuid
from app.core.gcp_clients import get_drive_service, get_firestore_client
from app.core.config import settings

def start_watching_drive(webhook_url: str = None):
    """
    구글 드라이브에 Webhook 알림(Watch)을 신청합니다.
    - webhook_url: Cloud Run 등 외부에서 접근 가능한 HTTPS URL 필수
    """
    service = get_drive_service()
    
    # URL이 없으면 설정이나 예시 값 사용 (실제 배포시는 필수)
    if not webhook_url:
        print("[Error] Webhook URL is required to start watching.")
        # 로컬 개발 시에는 ngrok 등을 써야 함
        return

    # 채널 ID 생성 (고유값)
    channel_id = str(uuid.uuid4())
    
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url
    }
    
    try:
        # 드라이브 전체 감시 (StartPageToken 사용 추천하지만 여기선 전체)
        # 1. StartPageToken 가져오기 (필수 파라미터)
        # 전체 드라이브를 감시하려면 "어디서부터" 감시할지 기준점이 필요함
        token_response = service.changes().getStartPageToken().execute()
        start_page_token = token_response.get('startPageToken')
        print(f"Got StartPageToken: {start_page_token}")

        # 2. Watch 요청 Send (pageToken 필수)
        print(f"Requesting Watch to: {webhook_url} (Channel: {channel_id})")
        response = service.changes().watch(body=body, pageToken=start_page_token).execute()
        
        result = {
            'resource_id': response['resourceId'],
            'channel_id': channel_id,
            'expiration': response.get('expiration'), 
            'url': webhook_url,
            'created_at': datetime.now()
        }

        # 3. 채널 정보를 DB에 저장 (나중에 stop() 할 때 필요)
        # 'system' 컬렉션에 현재 활성화된 채널 정보 저장
        get_firestore_client().collection('system').document('drive_channel_info').set(result, merge=True)
        
        print(f"Watch Started: {result}")
        return result
        
    except Exception as e:
        print(f"Failed to start watch: {str(e)}")
        raise e

# datetime import fix
# 비상용 수동 스위치로 터미널에서 직접 실행 가능하도록 구현
from datetime import datetime
import sys

if __name__ == "__main__":
    # 사용법: python -m app.utils.drive_watch https://my-cloud-run-url/webhook/drive
    if len(sys.argv) < 2:
        print("Usage: python -m app.utils.drive_watch <WEBHOOK_URL>")
        print("Example: python -m app.utils.drive_watch https://omnihub-backend-xyz.a.run.app/webhook/drive")
    else:
        url = sys.argv[1]
        print(f"Starting watch for URL: {url}...")
        start_watching_drive(webhook_url=url)
