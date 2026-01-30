import sys
sys.path.insert(0, '.')
import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'jnu-rise-edu-147'

from app.firestore_repo import get_client
from app.config import COL_CHUNKS

fs = get_client()

print("Firestore에 저장된 chunk 통계:")
print("="*60)

# Count total
count = 0
doc_ids = set()
for doc in fs.collection(COL_CHUNKS).limit(100).stream():
    count += 1
    d = doc.to_dict()
    parent_doc = d.get('parent_doc_id', 'Unknown')
    doc_ids.add(parent_doc)

print(f"총 chunk 개수 (샘플 100개): {count}")
print(f"고유 문서 개수: {len(doc_ids)}")
print(f"\n문서 ID 목록:")
for doc_id in sorted(doc_ids)[:20]:
    print(f"  - {doc_id}")

if len(doc_ids) > 20:
    print(f"  ... 외 {len(doc_ids) - 20}개")
