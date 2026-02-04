import os
import sys
from google.cloud import firestore
from dotenv import load_dotenv

# Load Env
# 상위 디렉토리의 .env 로드 시도
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv() # 현재 위치도 시도

def check_status(file_id: str):
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        print("❌ Error: GCP_PROJECT_ID not found in environment variables.")
        return

    print(f"📡 Connecting to Firestore (Project: {project_id})...")
    try:
        db = firestore.Client(project=project_id)
        
        print(f"🔍 Checking Document: {file_id}")
        doc_ref = db.collection("files").document(file_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            print("\n" + "="*40)
            print(f"📄 File Name       : {data.get('name', 'Unknown')}")
            print(f"🆔 Doc ID          : {file_id}")
            print(f"📊 Pipeline Status : {data.get('pipeline_status', 'Not started/Unknown')}")
            print(f"🤖 AI Status       : {data.get('aiStatus', 'Unknown')}")
            print("-" * 40)
            
            # Error Message
            if data.get('pipeline_error'):
                print(f"⚠️  ERROR DETAILS   : {data.get('pipeline_error')}")
            
            # Timestamp
            updated_at = data.get('pipeline_updated_at')
            if updated_at:
                print(f"🕒 Last Updated    : {updated_at}")
            
            # Chunks Check (Top-level 'chunks' collection)
            try:
                chunk_meta_doc = db.collection("chunks").document(file_id).get()
                if chunk_meta_doc.exists:
                    cm = chunk_meta_doc.to_dict()
                    c_count = cm.get("chunk_count", 0)
                    print(f"🧩 Chunks Status   : ✅ Created (Count: {c_count})")
                    print(f"📦 Chunks GCS URI  : {cm.get('gcs_chunks_uri', 'N/A')}")
                else:
                    print(f"🧩 Chunks Status   : ❌ Not found in 'chunks' collection")
            except Exception as e:
                print(f"🧩 Chunks Check    : Failed ({e})")
            
            # Profile Check
            try:
                profile_doc = db.collection("profiles").document(file_id).get()
                if profile_doc.exists:
                    p_data = profile_doc.to_dict()
                    p_title = p_data.get("title", "N/A (Missing)")
                    print(f"👤 Profile Title   : {p_title}")
                else:
                    print(f"👤 Profile Status  : ❌ Not found")
            except Exception as e:
                print(f"👤 Profile Check   : Failed ({e})")

            # Additional Info
            print("-" * 40)
            print(f"📂 Folder Path     : {data.get('folder_path', 'N/A')}")
            print(f"🔗 GCS URI         : {data.get('gcs_uri', 'N/A')}")
            print("="*40 + "\n")
        else:
            print(f"❌ Document {file_id} does not exist in Firestore 'files' collection.")
            
            # Prefix check hint
            if not file_id.startswith("fil_"):
                 print(f"💡 Hint: Try adding 'fil_' prefix -> fil_{file_id}")

    except Exception as e:
        print(f"❌ Failed to query Firestore: {e}")

if __name__ == "__main__":
    # Default ID from recent logs
    DEFAULT_ID = "fil_1U5U3yo5go0etcZ5KnDE5rpqkbYDw73Lc"
    
    target_id = DEFAULT_ID
    if len(sys.argv) > 1:
        target_id = sys.argv[1]
        
    check_status(target_id)
