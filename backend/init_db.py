import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime

# 1. 초기화 (로컬의 service_account.json 사용)
cred = credentials.Certificate("service_account.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def seed_dummy_file():
    file_id = "test-file-001"
    doc_ref = db.collection("files").document(file_id)
    
    # 더미 데이터 생성
    data = {
        "file_id": file_id,
        "name": "Project_Proposal_vFinal.pdf",
        "mime_type": "application/pdf",
        "size": 102450,
        "created_at": datetime.datetime.now(),
        "department_id": "SALES_DEPT", # AI-B가 볼 중요 정보
        "security_level": "CONFIDENTIAL", # AI-B가 볼 중요 정보
        "virtual_path": "/Sales/2026/Proposals"
    }
    
    doc_ref.set(data)
    print(f"✅ 테스트용 파일 데이터 생성 완료: {file_id}")
    print("   (이제 API로 이 파일을 조회하면 로그가 남습니다)")

if __name__ == "__main__":
    seed_dummy_file()
