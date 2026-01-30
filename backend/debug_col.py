import sys
sys.path.insert(0, '.')

# Setting environment
import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'jnu-rise-edu-147'

from app.firestore_repo import get_client
from app.config import COL_CHUNKS

fs = get_client()

print(f"COL_CHUNKS value: {COL_CHUNKS}")
print(f"Attempting to list from collection: {COL_CHUNKS}\n")

count = 0
for doc in fs.collection(COL_CHUNKS).limit(5).stream():
    count += 1
    d = doc.to_dict() or {}
    print(f"Doc {count}: {doc.id[:30]}")

print(f"\nTotal found: {count}")
