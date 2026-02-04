import os
from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv()

def fix_title(doc_id, title):
    db = firestore.Client(project=os.getenv("GCP_PROJECT_ID"))
    print(f"🔧 Fixing title for {doc_id} -> '{title}'")
    
    # 1. Update 'documents' collection
    db.collection("documents").document(doc_id).set({"title": title}, merge=True)
    print("✅ Updated 'documents' collection")
    
    # 2. Update 'profiles' collection
    db.collection("profiles").document(doc_id).set({"title": title}, merge=True)
    print("✅ Updated 'profiles' collection")

if __name__ == "__main__":
    doc_id = "fil_1U5U3yo5go0etcZ5KnDE5rpqkbYDw73Lc"
    title = "YES FTA 컨설팅 지원 사업 본격 실시.pdf"
    fix_title(doc_id, title)
