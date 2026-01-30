import urllib.request
import json

req = urllib.request.Request(
    'http://localhost:8000/api/chat',
    data=json.dumps({'question': '임대차 계약서의 핵심 내용을 3줄로 요약해줘', 'topK': 3}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    response = urllib.request.urlopen(req)
    result = json.loads(response.read())
    
    print('='*60)
    print('질문: 임대차 계약서의 핵심 내용을 3줄로 요약해줘')
    print('='*60)
    print('\n** AI Answer **')
    print(result['answer'])
    print('\n' + '='*60)
    
except Exception as e:
    print(f'Error: {e}')
