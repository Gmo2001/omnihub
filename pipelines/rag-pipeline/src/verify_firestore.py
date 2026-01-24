
import json
from google.cloud import firestore

def verify():
    project_id = 'jnu-rise-edu-147'
    try:
        db = firestore.Client(project=project_id)
        col = db.collection('omnihub_docs')
        docs = list(col.limit(1).stream())
        
        print(f"\n[Sanity Check] Collection: omnihub_docs")
        if not docs:
            print("Status: EMPTY")
        else:
            print("Status: OK")
            d = docs[0].to_dict()
            subset = {k: d.get(k) for k in ["id", "name", "driveUrl", "owner", "folderPath"]}
            print(f"Sample Doc (Subset): {json.dumps(subset, indent=2, ensure_ascii=False)}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()
