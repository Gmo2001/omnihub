import urllib.request
import json

req = urllib.request.Request(
    'http://localhost:8000/api/chat',
    data=json.dumps({'question': '계약서 관련 문서 알려줘', 'topK': 3}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    response = urllib.request.urlopen(req)
    result = json.loads(response.read())
    
    print('='*60)
    print('** AI Answer **')
    print(result['answer'][:600])
    print('\n' + '='*60)
    print(f'** Citations: {len(result["citations"])} documents **')
    
    for i, c in enumerate(result['citations'][:5]):
        print(f'\n[{i+1}] Doc ID: {c.get("doc_id", "N/A")[:40]}')
        print(f'    Page: {c.get("page", "N/A")}')
        print(f'    Snippet: {c.get("snippet", "")[:120]}...')
    
    print('='*60)
except Exception as e:
    print(f'Error: {e}')
