# utilly/mass_approve_chunks.py
from google.cloud import firestore
import os
from dotenv import load_dotenv

load_dotenv()
db = firestore.Client(project=os.getenv("GCP_PROJECT_ID"))

# 1. 'eng-001' 에 속한 모든 청크(chunks) 검색
# (참고: 컬렉션 이름이 'chunks' 인지 'omnihub_chunks' 인지 확인 필요)
chunks_ref = db.collection("chunks").where("engagement_id", "==", "eng-001")
chunks = chunks_ref.stream()

print("🚀 [eng-001] 모든 청크(Chunks) 승인 처리 시작...")
count = 0
batch = db.batch()

for chunk in chunks:
    batch.update(chunk.reference, {
        "review_status": "APPROVED",
        "active": True
    })
    count += 1
    
    # Firestore 배치 제한(500개) 고려
    if count % 400 == 0:
        batch.commit()
        batch = db.batch()

batch.commit()
print(f"✅ 총 {count}개의 청크가 승인되었습니다. 이제 RAG 테스트를 다시 실행해 보세요!")