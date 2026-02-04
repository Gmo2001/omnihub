import os
import sys
from google.cloud import firestore
from dotenv import load_dotenv

# Load Env
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv()

def debug_repo_logic(doc_id: str):
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        print("❌ GCP_PROJECT_ID missing")
        return

    db = firestore.Client(project=project_id)
    print(f"📡 Debugging for ID: {doc_id}")

    # 1. Fallback Imitation
    resolved_id = None
    snap = None
    
    # Try exact match
    ref = db.collection("documents").document(doc_id).get()
    if ref.exists:
        resolved_id = doc_id
        snap = ref
        print(f"✅ Found in 'documents' with ID: {doc_id}")
    else:
        print(f"❌ Not found in 'documents' with ID: {doc_id}")
        # Try fil_ prefix
        if not doc_id.startswith("fil_"):
            prefixed = f"fil_{doc_id}"
            ref_pre = db.collection("documents").document(prefixed).get()
            if ref_pre.exists:
                resolved_id = prefixed
                snap = ref_pre
                print(f"✅ Found in 'documents' with Prefix ID: {prefixed}")
            else:
                print(f"❌ Not found with Prefix ID: {prefixed}")
    
    if not resolved_id:
        print("💥 Document not found in 'documents' collection.")
        return

    # 2. Profile Merge Imitation
    print(f"🔍 Fetching Profile for resolved_id: {resolved_id}...")
    try:
        profile_snap = db.collection("profiles").document(resolved_id).get()
        if profile_snap.exists:
            p_data = profile_snap.to_dict()
            title = p_data.get("title")
            print(f"✅ Profile Found!")
            print(f"   - Title: '{title}'")
            print(f"   - Active: {p_data.get('active')}")
        else:
            print(f"❌ Profile Document does NOT exist for {resolved_id}")
            # Check if profile exists with original doc_id?
            if doc_id != resolved_id:
                print(f"   Checking original ID {doc_id} just in case...")
                ps2 = db.collection("profiles").document(doc_id).get()
                if ps2.exists:
                    print(f"   ! Profile exists for {doc_id}, but we used {resolved_id}")

    except Exception as e:
        print(f"❌ Error fetching profile: {e}")

if __name__ == "__main__":
    target_id = "fil_1U5U3yo5go0etcZ5KnDE5rpqkbYDw73Lc"
    if len(sys.argv) > 1:
        target_id = sys.argv[1]
    debug_repo_logic(target_id)
