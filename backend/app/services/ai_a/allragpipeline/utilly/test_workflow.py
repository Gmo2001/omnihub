import requests
import json

# 1. 설정 (사용자 환경에 맞게 수정하세요)
BASE_URL = "http://localhost:8000"
DOC_ID = "08ef43fabee6b8d058f14bd8d9f3ba388035c18b8f05a431db4ee2997785aa40"  # 실제 테스트할 문서 ID로 교체
TOKEN = "YOUR_ACCESS_TOKEN"    # 실제 토큰으로 교체 (필요 시)

def test_document_status_update():
    url = f"{BASE_URL}/api/docs/{DOC_ID}/status"
    
    # 2. 필수 헤더 설정 (서버 미들웨어 요구사항 반영)
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "X-User-Id": "test_admin",
        "X-Tenant-Id": "my-tenant",
        "X-Engagement-Id": "my-engagement"
    }
    
    # 3. 테스트 데이터 (한글 포함)
    payload = {
        "status": "APPROVED",  # REJECTED에서 변경
        "reason": "검토 결과 이상 없음. 승인합니다."
    }
    
    print(f"--- Requesting PATCH: {url} ---")
    
    try:
        # 4. 요청 보내기
        response = requests.patch(
            url, 
            headers=headers, 
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8')
        )
        
        # 5. 결과 출력
        if response.status_code == 200:
            print("✅ Success!")
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        else:
            print(f"❌ Failed (Status Code: {response.status_code})")
            print(response.text)
            
    except Exception as e:
        print(f"🚨 Error occurred: {e}")

if __name__ == "__main__":
    test_document_status_update()