import sys
sys.path.insert(0, '.')

from app.firestore_repo import get_client
from app.config import COL_CHUNKS

fs = get_client()

print("Sampling 3 chunks directly from Firestore...")
sample_chunks = []
for doc in fs.collection(COL_CHUNKS).limit(9).stream():
    d = doc.to_dict() or {}
    d.setdefault("chunk_id", doc.id)
    sample_chunks.append(d)

chunks = sample_chunks[:3]
print(f"Sampled {len(chunks)} chunks\n")

for i, c in enumerate(chunks):
    print(f"[{i+1}] Chunk ID: {c.get('chunk_id', 'N/A')[:30]}")
    print(f"    Doc ID: {c.get('parent_doc_id', 'N/A')[:40]}")
    print(f"    Page: {c.get('page', 'N/A')}")
    snippet = c.get('snippet', c.get('content', 'N/A'))
    print(f"    Content: {snippet[:150]}...\n")
