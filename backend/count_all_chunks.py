import sys
sys.path.insert(0, '.')
import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'jnu-rise-edu-147'

from app.firestore_repo import get_client
from app.config import COL_CHUNKS

fs = get_client()

print("Firestore 전체 chunk 개수 확인 중...")
print("="*60)

# Count ALL chunks (no limit)
total_count = 0
for _ in fs.collection(COL_CHUNKS).stream():
    total_count += 1
    if total_count % 100 == 0:
        print(f"진행 중... {total_count}개")

print(f"\n최종 결과: 총 {total_count}개의 chunk가 Firestore에 저장되어 있습니다.")
print("="*60)
