from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import time

class RequestScope(BaseModel):
    folder_path: Optional[str] = None
    doc_ids: Optional[List[str]] = None
    concept_ids: Optional[List[str]] = None

class AuthContext(BaseModel):
    user_id: str
    tenant_id: str
    engagement_id: str
    roles: List[str] = []
    
    # Optional Scope (Per Request)
    request_scope: Optional[RequestScope] = None
    
    # Trace Info
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    timestamp: float = 0.0 # Default to avoid errors if not set
