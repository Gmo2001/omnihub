from typing import List, Dict
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from .config import PROJECT_ID, VERTEX_LOCATION, GEMINI_MODEL

def build_context(chunks: List[Dict]) -> str:
    # Provide more content for better understanding
    lines = []
    for i, c in enumerate(chunks, 1):
        chunk_id = c.get("chunk_id") or c.get("chunk_id")
        doc_id = c.get("parent_doc_id", "")
        page = c.get("page", 1)
        # Use longer snippets (up to 500 chars)
        snippet = c.get("snippet", "") or c.get("content", "")
        snippet = snippet[:500] if snippet else "(내용 없음)"
        lines.append(f"[문서{i}] chunk_id={chunk_id} | doc_id={doc_id} | page={page}\n내용: {snippet}\n")
    return "\n".join(lines)

def answer_with_citations(question: str, chunks: List[Dict]) -> str:
    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    model = GenerativeModel(GEMINI_MODEL)

    context = build_context(chunks)

    prompt = f"""당신은 문서 기반 질의응답 전문가입니다.
아래 제공된 문서 내용을 기반으로 사용자의 질문에 답변해주세요.

**중요 지침:**
1. 제공된 문서 내용을 최대한 활용하여 유용한 답변을 제공하세요
2. 문서에서 관련 정보를 찾았다면 요약하거나 재구성하여 답변하세요
3. 정말 관련 정보가 전혀 없을 때만 "근거 부족"이라고 하세요
4. 답변 시 어떤 문서를 참고했는지 chunk_id를 명시하세요

**질문:**
{question}

**참고 문서:**
{context}

**답변 형식:**
- 답변: (질문에 대한 구체적이고 유용한 답변)
- 근거: 사용한 chunk_id들을 쉼표로 나열
"""
    resp = model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.4,  # Increased for more creative responses
            max_output_tokens=1000
        )
    )
    return (resp.text or "").strip()
