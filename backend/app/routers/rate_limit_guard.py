import os
import time
import logging
import hashlib
from typing import Optional, Dict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from google.cloud import firestore

from dotenv import load_dotenv
load_dotenv()
from app.core.gcp_clients import get_firestore_client

# --- Configurations ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
RATE_LIMIT_MODE = os.getenv("RATE_LIMIT_MODE", "firestore")
WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", 60))
FIRESTORE_DB = os.getenv("FIRESTORE_DATABASE", "(default)")

# Simple Policy Map: {path_prefix: (limit, scope)}
# scope: "user" | "tenant"
LIMIT_RULES = {
    "/api/graph/init": (60, "tenant"),
    "/api/search/rag": (30, "user"),
    "/api/docs": (120, "tenant"),     # prefix matching
    # default fallback
}
DEFAULT_LIMIT = (120, "tenant")

logger = logging.getLogger("RateLimitGuard")

# --- Helper Logic ---
def get_limit_config(path: str):
    # Longest prefix match
    best_match = DEFAULT_LIMIT
    max_len = 0
    
    for prefix, config in LIMIT_RULES.items():
        if path.startswith(prefix) and len(prefix) > max_len:
            best_match = config
            max_len = len(prefix)
    
    return best_match

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 0. Skip Healthz
        if request.url.path == "/healthz":
            return await call_next(request)
            
        # 1. Get Auth Context
        auth_ctx = getattr(request.state, "auth_ctx", None)
        if not auth_ctx:
            # 인증 실패했으면 RateLimit 스킵 (어차피 401 나감)
            return await call_next(request)
            
        # 2. Determine Key
        limit, scope = get_limit_config(request.url.path)
        
        tenant_id = auth_ctx.tenant_id
        user_id = auth_ctx.user_id
        
        # Time Window Key (YYYYMMDDHHMM) -> 분 단위
        now = time.time()
        time_key = time.strftime("%Y%m%d%H%M", time.gmtime(now))
        
        # Key Construction
        if scope == "user":
            key_raw = f"{tenant_id}:{user_id}:{request.url.path}:{time_key}"
        else:
            key_raw = f"{tenant_id}:{request.url.path}:{time_key}"
            
        hashed_key = hashlib.md5(key_raw.encode()).hexdigest()
        doc_key = f"rate_limits/{hashed_key}"
        
        # 3. Check Limit (Firestore Transaction)
        try:
            allowed, current_count = self.increment_counter(doc_key, limit)
        except Exception as e:
            logger.error(f"RateLimit Check Failed: {e}")
            # Fail Open (운영 안정성 위해 에러 시 통과)
            allowed = True
            current_count = 0

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited", 
                    "message": "Too many requests. Please try again later.",
                    "retry_after_sec": 60,
                    "limit": limit
                }
            )

        # 4. Success -> Call Next
        response = await call_next(request)
        
        # Optional Hints
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
        
        return response

    def increment_counter(self, doc_path: str, limit: int) -> (bool, int):
        """Transactional Increment"""
        if RATE_LIMIT_MODE == "memory":
            # 여기선 간단히 항상 통과 (운영 최소 픽스는 firestore)
            return True, 0
            
        transaction = get_firestore_client().transaction()
        doc_ref = get_firestore_client().document(doc_path)
        
        @firestore.transactional
        def update_in_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            current = 0
            if snapshot.exists:
                current = snapshot.get("count")
            
            if current >= limit:
                return False, current
            
            new_count = current + 1
            if not snapshot.exists:
                transaction.set(ref, {
                    "count": new_count,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
            else:
                transaction.update(ref, {"count": new_count})
            
            return True, new_count
            
        return update_in_transaction(transaction, doc_ref)
