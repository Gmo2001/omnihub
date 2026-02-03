
import firebase_admin
from firebase_admin import credentials, firestore
import logging
from dotenv import load_dotenv
import os

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB-Cleaner")

# .env 로드
load_dotenv()

def delete_collection(db, collection_ref, batch_size):
    docs = collection_ref.limit(batch_size).stream()
    deleted = 0

    for doc in docs:
        logger.info(f"Deleting doc {doc.id} => {doc.reference.path}")
        doc.reference.delete()
        deleted = deleted + 1

    if deleted >= batch_size:
        return delete_collection(db, collection_ref, batch_size)

def main():
    # 1. Firebase 초기화 (이미 실행 중이면 건너뜀)
    try:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path:
             print("❌ GOOGLE_APPLICATION_CREDENTIALS 환경변수가 설정되지 않았습니다.")
             return
             
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    except Exception:
        pass # 이미 초기화된 경우 무시

    db = firestore.client()
    
    # 2. 삭제할 컬렉션 목록
    collections_to_clear = [
        "docai_results",
        "profiles",
        "policies",
        "doc_chunks", # chunks vs doc_chunks 확인 필요 (둘다 넣음)
        "chunks",
        "cards",
        "entities",
        "doc_bundles",
        "edges_doc_concept",
        "vector_upserts",
        "documents",
        "files" # 원본 파일 메타데이터도 삭제하고 싶다면 포함
    ]

    print("🔥 [DB Cleaner] 파이프라인 데이터 삭제 시작...")
    
    for col_name in collections_to_clear:
        col_ref = db.collection(col_name)
        # 문서가 있는지 확인
        docs = list(col_ref.limit(1).stream())
        if not docs:
            print(f"   [Skip] {col_name} (비어있음)")
            continue
            
        print(f"   🗑️ Deleting {col_name}...")
        # 재귀적 삭제 호출
        delete_collection(db, col_ref, 100)
        
    print("✨ 모든 데이터 삭제 완료!")

if __name__ == "__main__":
    main()
