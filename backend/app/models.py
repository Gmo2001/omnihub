from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class ChatFilters(BaseModel):
    securityLevel: Optional[str] = None
    department: Optional[str] = None
    docStatus: Optional[str] = None
    fileIds: Optional[List[str]] = None

class ChatRequest(BaseModel):
    question: str
    filters: Optional[ChatFilters] = None
    topK: int = 8

class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    page: int = 1
    source_uri: str = ""
    snippet: str = ""

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)

class InitialDataResponse(BaseModel):
    docs: List[Dict[str, Any]]
    concepts: List[Dict[str, Any]]

class EvidenceGraphResponse(BaseModel):
    docs: List[Dict[str, Any]]
    concepts: List[Dict[str, Any]]
    citations: List[Citation] = Field(default_factory=list)
