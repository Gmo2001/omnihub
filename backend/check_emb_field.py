from app.firestore_repo import get_client
from app.config import COL_CHUNKS
import sys

fs = get_client()
print("Checking first chunk for 'embedding' field...")

for doc in fs.collection(COL_CHUNKS).limit(1).stream():
    d = doc.to_dict()
    if 'embedding' in d:
        print(f"✅ Found embedding field! Length: {len(d['embedding'])}")
    else:
        print("❌ No 'embedding' field in Firestore document.")
    
    print(f"Keys: {list(d.keys())}")
