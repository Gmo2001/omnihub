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
