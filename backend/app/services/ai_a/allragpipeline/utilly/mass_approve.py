# mass_approve.py 로 저장 후 실행
from google.cloud import firestore
import os
from dotenv import load_dotenv

load_dotenv()
db = firestore.Client(project=os.getenv("GCP_PROJECT_ID"))

# eng-001 에 속한 모든 문서 검색
docs = db.collection("documents").where("engagement_id", "==", "eng-001").stream()

print("🚀 모든 문서 승인 처리 중...")
count = 0
for doc in docs:
    doc.reference.update({
        "review_status": "APPROVED",
        "active": True,
        "graph_visible": True
    })
    count += 1

print(f"✅ 총 {count}개의 문서가 승인되었습니다. 이제 RAG 테스트를 다시 해보세요!")