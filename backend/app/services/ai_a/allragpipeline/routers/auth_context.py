import os
import time
import uuid
from typing import Optional, List
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

# Auth Config
AUTH_MODE = os.getenv("AUTH_MODE", "header")

from app.services.ai_a.allragpipeline.common.types import AuthContext
from app.core.config import settings
from jose import jwt, JWTError
from app.core.gcp_clients import db
import logging

logger = logging.getLogger("AuthContext")

class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Health check 등은 인증 제외 가능 (여기선 그냥 통과)
        # 1. Exclude Public Paths / Health Checks / OPTIONS (CORS)
        public_paths = ["/healthz", "/api/health", "/docs", "/redoc", "/openapi.json"]
        if request.method == "OPTIONS" or request.url.path in public_paths or request.url.path.startswith("/auth/") or request.url.path.startswith("/static"):
            return await call_next(request)

        # 2. Extract Headers
        user_id = request.headers.get("X-User-Id")
        tenant_id = request.headers.get("X-Tenant-Id")
        engagement_id = request.headers.get("X-Engagement-Id")
        roles_header = request.headers.get("X-User-Roles", "")
        department_id = None # [RBAC] Initialize
        
        # Request/Trace ID
        # 없으면 생성, 있으면 유지 (Trace Propagation)
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        trace_id = request.headers.get("X-Trace-Id", request_id) # 간단히 req_id와 동일하게 시작
        
        # 3. Validate (AUTH_MODE=header 일 때)
        if AUTH_MODE == "header":
            # [Updated Logic] Token-based "Translator" Mode
            # If "Authorization" header exists, use it to resolve User/Tenant/Engagement
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                try:
                    # 1. Decode Token
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                    email = payload.get("sub")
                    
                    if email:
                        # 2. Fetch User from DB
                        user_ref = db.collection("users").document(email).get()
                        if user_ref.exists:
                            user_data = user_ref.to_dict()
                            
                            # 3. Populate IDs from User Data (The "Translation" Step)
                            user_id = user_data.get("user_id", email) # Fallback to email if no user_id
                            # Default to first available tenant/engagement or use specific fields
                            # Assuming user_data has 'active_tenant_id' or we pick one?
                            # For now, let's look for known fields or use defaults
                            tenant_id = user_data.get("active_tenant_id") or user_data.get("tenant_id") or "default-tenant"
                            engagement_id = user_data.get("active_engagement_id") or "default-engagement"
                            department_id = user_data.get("department_id") # [RBAC] Fetch Department ID
                            
                            # Update Roles
                            db_roles = user_data.get("roles", [])
                            if db_roles:
                                roles_header = ",".join(db_roles) # Will be split below
                                
                except Exception as e:
                    logger.warning(f"Token translation failed: {e}")
                    # Fallback to standard header check below

            # 운영 최소: 필수 헤더 체크
            missing = []
            if not user_id: missing.append("X-User-Id")
            if not tenant_id: missing.append("X-Tenant-Id")
            if not engagement_id: missing.append("X-Engagement-Id")
            
            if missing:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Unauthorized",
                        "message": f"Missing Auth Context (Headers or Valid Token). Missing: {', '.join(missing)}",
                        "request_id": request_id
                    }
                )
        elif AUTH_MODE == "mock":
            # 개발용 Mock
            user_id = user_id or "mock-user"
            tenant_id = tenant_id or "tenant-001"
            engagement_id = engagement_id or "eng-001"
        
        # 4. Build Context
        roles = [r.strip() for r in roles_header.split(",") if r.strip()]
        
        ctx = AuthContext(
            user_id=user_id,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            department_id=department_id, # [RBAC]
            roles=roles,
            request_id=request_id,
            trace_id=trace_id,
            timestamp=time.time()
        )
        
        # 5. Inject to State
        request.state.auth_ctx = ctx
        
        # 6. Call Next
        response = await call_next(request)
        
        # 7. Response Headers
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        
        return response
