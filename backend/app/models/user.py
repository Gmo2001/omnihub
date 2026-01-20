from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

#추후 로그인 기능과 함께 사용할 모델
class UserSchema(BaseModel):
    # ==========================================
    # [Identity Provider Info] 담당자: Auth/Frontend 🔐
    # - Google/Firebase Auth에서 제공하는 기본 정보입니다.
    # ==========================================
    uid: str              # Firebase User UID (Primary Key)
    email: EmailStr       # 이메일
    display_name: str     # 이름
    photo_url: Optional[str] = None # 프로필 사진 URL

    # ==========================================
    # [Organization Info] 담당자: HR/Admin 🏢
    # - 회사 내 조직 정보 및 권한입니다.
    # ==========================================
    department: Optional[str] = None # 부서 (예: "개발팀", "마케팅팀")
    position: Optional[str] = None   # 직책 (예: "팀장", "매니저")
    role: str = Field(default="user") # user, admin, manager

    # ==========================================
    # [System Info] 담당자: Backend ⚙️
    # ==========================================
    created_at: datetime = Field(default_factory=datetime.now)
    last_login_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True # 퇴사자 처리 등시 False  or 보안위협시 긴급 차단용으로 사용도 가능하도록 만듬
    
    # User Settings (Optional)
    preferences: dict = Field(default_factory=dict) # 알림 설정 등

class UserResponse(UserSchema):
    pass
