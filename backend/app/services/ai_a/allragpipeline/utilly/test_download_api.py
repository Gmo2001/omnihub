import requests
import json

BASE_URL = "http://localhost:8000"
# 이전에 성공했던 그 문서 ID와 테넌트 정보를 사용하세요!
DOC_ID = "08ef43fabee6b8d058f14bd8d9f3ba388035c18b8f05a431db4ee2997785aa40"

def test_secure_download():
    url = f"{BASE_URL}/api/docs/{DOC_ID}/download"
    headers = {
        "Authorization": "Bearer dummy_token",
        "X-User-Id": "admin_user",
        "X-Tenant-Id": "my-tenant",
        "X-Engagement-Id": "my-engagement"
    }

    print(f"--- Requesting Download Link: {url} ---")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        print("✅ Success! Signed URL Generated.")
        print(f"🔗 URL: {data['url'][:100]}...") # 너무 길어서 앞부분만 출력
        print(f"⏳ Expires in: {data['expires_in_seconds']}s")
        
        # 실제 브라우저에서 열 수 있는지 확인해보세요!
        return data['url']
    else:
        print(f"❌ Failed: {response.status_code}")
        print(response.text)
        return None

if __name__ == "__main__":
    test_secure_download()