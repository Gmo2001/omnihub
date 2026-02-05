# main_app.py
import os
from flask import Flask, request
import pipeline  # 기존에 만드신 pipeline.py를 불러옵니다.

app = Flask(__name__)

@app.route("/", methods=["POST"])
def run_pipeline():
    try:
        print("[EVENT] 로그 유입 감지, 파이프라인 실행 시작...")
        pipeline.main()  # 기존 pipeline.py의 main 함수 실행
        return "Pipeline Executed Successfully", 200
    except Exception as e:
        print(f"[ERROR] 파이프라인 실행 실패: {e}")
        return f"Error: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))