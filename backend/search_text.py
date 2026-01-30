import sys
sys.path.insert(0, '.')
import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'jnu-rise-edu-147'

from app.firestore_repo import get_client
from app.config import COL_CHUNKS

fs = get_client()

search_term = "파월"
print(f"Firestore에서 '{search_term}' 텍스트 검색 중...")
print("="*80)

found = []
total = 0

for doc in fs.collection(COL_CHUNKS).limit(200).stream():
    total += 1
    d = doc.to_dict()
    chunk_id = doc.id
    snippet = d.get('snippet', '')
    content = d.get('content', '')
    
    if search_term in snippet or search_term in content:
        found.append({
            'chunk_id': chunk_id,
            'parent_doc': d.get('parent_doc_id', 'N/A'),
            'page': d.get('page', 'N/A'),
            'snippet': snippet[:200] if snippet else content[:200]
        })

print(f"총 {total}개 chunk 검색 완료")
print(f"'{search_term}' 포함된 chunk: {len(found)}개\n")

if found:
    for i, item in enumerate(found[:10], 1):
        print(f"[{i}] Chunk ID: {item['chunk_id']}")
        print(f"    Doc: {item['parent_doc']} | Page: {item['page']}")
        print(f"    내용: {item['snippet']}\n")
else:
    print(f"❌ '{search_term}'이(가) 포함된 chunk가 없습니다!")
    print("OCR/청킹 문제일 가능성이 높습니다.")
