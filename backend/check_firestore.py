from google.cloud import firestore

PROJECT_ID = "jnu-rise-edu-147"
FIRESTORE_DATABASE = "(default)"
COL_CHUNKS = "omnihub_chunks"

fs = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)

# Count chunks
count = 0
for doc in fs.collection(COL_CHUNKS).limit(10).stream():
    count += 1
    d = doc.to_dict()
    print(f"Chunk {count}: {doc.id[:20]}... | parent_doc: {d.get('parent_doc_id', 'N/A')[:30]} | snippet: {d.get('snippet', d.get('content', 'N/A'))[:80]}")

print(f"\nTotal chunks found (sample): {count}")
