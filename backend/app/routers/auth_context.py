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

from app.common.types import AuthContext

class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Health check 등은 인증 제외 가능 (여기선 그냥 통과)
        if request.url.path == "/healthz":
            return await call_next(request)

        # 2. Extract Headers
        user_id = request.headers.get("X-User-Id")
        tenant_id = request.headers.get("X-Tenant-Id")
        engagement_id = request.headers.get("X-Engagement-Id")
        roles_header = request.headers.get("X-User-Roles", "")
        
        # Request/Trace ID
        # 없으면 생성, 있으면 유지 (Trace Propagation)
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        trace_id = request.headers.get("X-Trace-Id", request_id) # 간단히 req_id와 동일하게 시작
        
        # 3. Validate (AUTH_MODE=header 일 때)
        if AUTH_MODE == "header":
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
                        "message": f"Missing headers: {', '.join(missing)}",
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
