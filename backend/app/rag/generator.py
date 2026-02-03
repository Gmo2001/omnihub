import os
import logging
import json
from typing import List, Dict, Any, Optional
import vertexai
from vertexai.generative_models import GenerativeModel, SafetySetting

logger = logging.getLogger("Generator")

# --- Env Config ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-exp")
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT_CHUNKS", 10))

class Generator:
    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        self.model = GenerativeModel(MODEL_NAME)
        
        # Safety Settings (운영 최소: 일부 필터 완화 가능하나 기본 유지)
        self.safety_settings = [
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
             SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
             SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
        ]

    def _format_context(self, chunks: List[Dict]) -> str:
        """
        검색된 청크들을 프롬프트에 주입할 컨텍스트 문자열로 변환
        Format:
        [1] {title} (Page {page})
        {text}
        ...
        """
        context_parts = []
        for idx, chunk in enumerate(chunks[:MAX_CONTEXT]):
            # chunk key validation
            doc_title = chunk.get("doc_title", "Untitled")
            page = chunk.get("page", "?")
            # [Fix] Support both 'text' (legacy) and 'snippet' (Evidence schema)
            text = chunk.get("text") or chunk.get("snippet") or ""
            text = text.strip()
            
            part = f"[{idx+1}] Source: {doc_title} (Page {page})\nContent: {text}"
            context_parts.append(part)
            
        return "\n\n".join(context_parts)

    def generate(self, query: str, chunks: List[Dict]) -> str:
        if not chunks:
            return "검색 결과가 없어 답변을 생성할 수 없습니다."
            
        context_str = self._format_context(chunks)
        
        # System Prompt (Expert Persona + Rules)
        # Markdown 포맷 강제
        system_instruction = """
당신은 회계/법률 분야의 전문 AI 어시스턴트 'Omnihub AI'입니다.
사용자의 질문에 대해 제공된 [Context]만을 바탕으로 답변해야 합니다.
없는 사실을 지어내지 마십시오. 정보가 부족하면 솔직히 말하세요.

[답변 구조]
1. **요약 결론**: 질문에 대한 핵심 답변을 두괄식으로 요약 (확정적 표현 자제).
2. **상세 판단 근거**: Context의 내용을 바탕으로 논리적으로 설명 (Bullet point 활용).
3. **리스크/확인 필요 사항**: 정보의 한계나 추가 확인이 필요한 리스크 요소 언급.
4. **References**: 인용된 문서를 [1], [2] 형태로 나열 (이미 답변 본문에 인용 표시가 있어야 함).

[작성 규칙]
- 답변 본문 중 문장 끝에 관련 출처 번호를 반드시 명시하세요. 예: ...라고 규정되어 있습니다[1].
- 한국어로 답변하십시오.
- 전문적인 톤앤매너를 유지하십시오.
"""
        
        full_prompt = f"""
{system_instruction}

[Context]
{context_str}

[Question]
{query}

[Answer]
"""
        try:
            response = self.model.generate_content(
                full_prompt,
                safety_settings=self.safety_settings,
                generation_config={
                    "max_output_tokens": 2048,
                    "temperature": 0.2, # 낮은 온도 (사실 기반)
                    "top_p": 0.8
                }
            )
            return response.text
        except Exception as e:
            logger.error(f"Generation Failed: {e}")
            return "죄송합니다. 답변 생성 중 오류가 발생했습니다."
