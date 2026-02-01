from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

from pydantic.alias_generators import to_camel

class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel
        populate_by_name = True

class AIInsightSchema(CamelModel):
      # => 결과에 대한 요소? 변수 등을 넣기. 연결고리용 - > 이걸로 api를 만들겠다.
    """
    [Phase 3] AI 분석 결과 전용 모델 (Fact와 Insight 분리)
    - 원본 파일 정보(files)와 1:N 또는 1:1 관계
    추후 결과를 반영해서 스키마 작성을 해주세요
    아래는 예시입니다.
    """
    file_id: str = Field(..., description="원본 파일 ID (FK)")
    
    
    """
    # 분석 메타데이터
    model_name: str = Field(..., description="분석에 사용된 모델 (예: gemini-1.5-pro)")
    model_version: str = Field("v1.0", description="모델/프롬프트 버전")
    analyzed_at: datetime = Field(default_factory=datetime.utcnow, description="분석 완료 시간")
    
    # 분석 결과 (Core Insights)
    summary: str = Field(..., description="문서 3줄 요약")
    keywords: List[str] = Field(default=[], description="핵심 키워드 5개")
    category: str = Field(..., description="자동 분류 카테고리 (예: 계약서, 보고서)")
    
    # 선택적 심화 분석
    sentiment: Optional[str] = Field(None, description="어조/감정 분석 (긍정/부정/중립)")
    action_items: List[str] = Field(default=[], description="도출된 실행 과제(To-Do)")
    
    # RAG/Vector Search용
    vector_id: Optional[str] = Field(None, description="Vector DB 저장 ID")
    """

  