import os
from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv()

# Firestore 클라이언트 초기화
db = firestore.Client(
    project=os.getenv("GCP_PROJECT_ID"), 
    database=os.getenv("FIRESTORE_DATABASE", "(default)")
)

# 1. profiles 컬렉션의 모든 문서를 가져옵니다.
docs = db.collection("profiles").where("active", "==", True).stream()

print("엔티티 추출 플래그 리셋 시작...")

for doc in docs:
    # 2. 각 문서의 entities 플래그를 다시 True로 바꿉니다.
    doc.reference.update({
        "process_flags.entities": True
    })
    print(f"Reset SUCCESS: {doc.id}")

print("모든 문서의 추출 준비가 완료되었습니다!")