import sys
import os

# 현재 파일의 부모의 부모 폴더(Root)를 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.permission_guard import PermissionGuard
from fastapi import HTTPException
from dataclasses import dataclass
from typing import List



@dataclass
class MockAuthCtx:
    user_id: str
    tenant_id: str
    engagement_id: str
    roles: List[str]

# 1. 테스트 데이터 준비
mock_doc = {
    "doc_id": "secret_123",
    "tenant_id": "my-tenant",
    "engagement_id": "project-A",
    "review_status": "PENDING",
    "security_level": "High"
}

# 2. 시나리오 테스트
def run_security_test():
    # 케이스 A: 타사 사용자가 접근할 때 (Tenant Mismatch)
    hacker_ctx = MockAuthCtx("hacker", "other-tenant", "project-A", ["user"])
    print("Test 1: Cross-tenant access ->", end=" ")
    try:
        PermissionGuard.ensure_doc_access(hacker_ctx, mock_doc)
    except HTTPException as e:
        print(f"✅ Blocked (Status: {e.status_code}, Detail: {e.detail})")

    # 케이스 B: 같은 테넌트지만 승인되지 않은 문서를 일반 유저가 볼 때
    user_ctx = MockAuthCtx("user1", "my-tenant", "project-A", ["user"])
    print("Test 2: Non-approved doc access (Normal User) ->", end=" ")
    try:
        PermissionGuard.ensure_doc_access(user_ctx, mock_doc)
    except HTTPException as e:
        print(f"✅ Blocked (Status: {e.status_code}, Detail: {e.detail})")

    # 케이스 C: 관리자가 접근할 때
    admin_ctx = MockAuthCtx("admin1", "my-tenant", "project-A", ["admin"])
    print("Test 3: Admin access to Pending/High Doc ->", end=" ")
    if PermissionGuard.ensure_doc_access(admin_ctx, mock_doc):
        print("✅ Access Granted")

if __name__ == "__main__":
    run_security_test()