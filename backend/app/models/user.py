from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from pydantic.alias_generators import to_camel
from app.common.id_utils import to_internal_id
from datetime import datetime

# CamelCase 변환 설정을 위한 Base Model
class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel
        populate_by_name = True

#추후 로그인 기능과 함께 사용할 모델
class UserSchema(CamelModel):
    # ==========================================
    # [Identity Provider Info] 담당자: Auth/Frontend 🔐
    # - Google/Firebase Auth에서 제공하는 기본 정보입니다.
    # ==========================================
    user_id: str = Field(alias="userId") # Firebase User UID (Primary Key) -> usr_XXX
    
    # ID Prefix 강제 적용 (Validator 대신 Setter/Init 시점에 처리 권장되지만, Pydantic v1/v2 차이 고려)
    # 여기서는 input 값이 들어올 때 prefix가 없으면 붙여주는 로직이 서비스 레이어에 있어야 함.
    # 혹은 custom validator 사용.
    
    email: EmailStr       # 이메일
    email: EmailStr       # 이메일
    display_name: str     # 이름
    photo_url: Optional[str] = None # 프로필 사진 URL
    google_access_token: Optional[str] = None # Encrypted Access Token
    google_refresh_token: Optional[str] = None # Encrypted Refresh Token

    # 별칭(Alias) 호환성 유지: uid -> user_id
    @property
    def uid(self):
        return self.user_id

    # ==========================================

    # ==========================================
    # [Organization Info] 담당자: HR/Admin 🏢
    # - 회사 내 조직 정보 및 권한입니다.
    # ==========================================
    department: Optional[str] = None # 부서명 (예: "개발팀")
    department_id: Optional[str] = None # 부서 코드 (예: "DEPT_DEV") - AI-B 학습용

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
    monitored_folder_ids: List[str] = Field(default_factory=list) # [Privacy] Whitelisted Folder IDs

class UserResponse(UserSchema):
    pass
