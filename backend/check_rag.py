import urllib.request
import urllib.error
import json
import sys

API_URL = "http://localhost:8000/api/chat"

def red(s): return f"\033[91m{s}\033[0m"
def green(s): return f"\033[92m{s}\033[0m"
def cyan(s): return f"\033[96m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"

def chat(question):
    data = {
        "question": question,
        "topK": 5,
        "filters": {}
    }
    
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                print(red(f"Error: {response.status}"))
                # Read body just in case
                print(response.read().decode('utf-8'))
                return

            res_body = response.read()
            res_json = json.loads(res_body)

            print("\n" + "="*60)
            print(f"🤖 {green('AI 답변')}:")
            print(res_json.get("answer"))
            print("="*60)
            
            citations = res_json.get("citations", [])
            if citations:
                print(f"\n📚 {cyan('참고 문서 (Evidence)')}: {len(citations)}건")
                for i, c in enumerate(citations):
                    title = c.get('source_uri', 'Unknown').split('/')[-1]
                    snippet = c.get('snippet', '').replace('\n', ' ')[:100]
                    print(f"  [{i+1}] {yellow(title)} (p.{c.get('page')})")
                    print(f"      \"{snippet}...\"")
            else:
                print(f"\n{red('참고 문서 없음')}")
            print("\n")

    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        print(red(f"HTTP Error {e.code}: {e.reason}"))
        print(yellow(f"Server Response: {err_body}"))
    except Exception as e:
        print(red(f"통신 에러 발생: {e}"))
        print(f"백엔드 서버(localhost:8000)가 켜져 있는지 확인해주세요.")

def main():
    print(f"{green('OmniHub RAG CLI Tester')} (Backend: {API_URL})")
    print("프론트엔드 없이 터미널에서 바로 RAG 품질을 테스트합니다.")
    print("-" * 50)

    while True:
        try:
            q = input(f"{cyan('질문을 입력하세요')} (종료: q, exit): ").strip()
            if q.lower() in ('q', 'exit', 'quit'):
                print("종료합니다.")
                break
            if not q:
                continue
            
            chat(q)
        except KeyboardInterrupt:
            print("\n종료합니다.")
            break

if __name__ == "__main__":
    main()
