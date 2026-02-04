from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    """
    Standard Evidence Schema
    """
    doc_id: str
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    source_link: Optional[str] = None
    span: Optional[Dict[str, int]] = None # {"start": 0, "end": 100}
    snippet: Optional[str] = Field(None, description="Short text capture, usually < 300 chars")
    title: Optional[str] = None # Added for Context

class Citation(BaseModel):
    """
    Standard Citation Schema (Used in RAG Response)
    """
    idx: int = Field(..., description="Citation Index (1-based)")
    doc_id: str
    title: Optional[str] = None
    source_link: Optional[str] = None
    page: Optional[int] = None
    chunk_id: Optional[str] = None
    snippet: Optional[str] = None

class RAGResponse(BaseModel):
    answer: str
    citations: List[Citation]
    meta: Dict[str, Any] = {}

class AIAnalysisRequest(BaseModel):
    """
    [Phase 3 Handoff DTO]
    AI-A 개발자(Analysis Service)에게 전달되는 표준 요청 규격입니다.
    DB를 조회하지 않고도 분석에 필요한 모든 정보(Content + Context)를 포함해야 합니다.
    """
    # 1. 원본 소스 (Content)
    file_id: str = Field(..., description="결과 저장 및 추적을 위한 ID")
    gcs_uri: Optional[str] = Field(None, description="GCS 원본 파일 경로 (멀티모달 분석용)")
    mime_type: str = Field(..., description="파일 타입 (분석 모델 선택 기준)")
    
    # 텍스트가 이미 추출된 경우 (선택)
    extracted_text: Optional[str] = Field(None, description="Ingestion 단계에서 추출된 텍스트 (텍스트 전용 모델용)")

    # 2. 맥락 정보 (Context) - 프롬프트 엔지니어링용
    file_name: str = Field(..., description="파일명 (주제 유추용)")
    full_path: Optional[str] = Field(None, description="폴더 경로 (업무 맥락 유추용)")
    owners: List[str] = Field(default=[], description="소유자 (작성자)")
    last_modified_by: Optional[str] = Field(None, description="마지막 수정자")
