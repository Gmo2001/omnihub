from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from app.utils.id_utils import to_internal_id
from datetime import datetime
from typing import Optional
from enum import Enum

# 행동 종류 정의 (Enum)
class ActionType(int, Enum):
    VIEW = 0            # 조회
    DOWNLOAD = 1        # 다운로드
    MOVE = 2            # 이동
    APPROVE = 3         # 승인
    DENIED = 4          # 접근 거부
    LOGIN = 5           # 로그인
    LOGOUT = 6          # 로그아웃
    DELETE = 7          # 영구 삭제
    TRASH = 8           # 휴지통 이동
    CREATE = 9          # 파일 생성 (최초 수집)
    UPDATE = 10         # 파일 수정 (업데이트)

# CamelCase Model
class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel
        populate_by_name = True

# Firestore 'logs' 컬렉션 구조
class LogSchema(CamelModel):
    # ==========================================
    # 1. 이벤트 필수 정보 (Event Basics) - AI-B Spec
    # ==========================================
    event_ts: datetime = Field(default_factory=datetime.utcnow, alias="eventTs") # UTC Time
    
    action_type: int = Field(alias="actionType") # 0~4 (Int)
    
    # ==========================================
    # 2. 주체 식별자 (Who)
    # ==========================================
    user_id: str = Field(alias="userId") # 사용자 ID (usr_xxx)
    user_department_id: Optional[str] = Field(None, alias="userDepartmentId") # (dpt_xxx)
    
    # ==========================================
    # 3. 객체 식별자 (What)
    # ==========================================
    file_id: Optional[str] = Field(None, alias="fileId") # 파일 ID (fil_xxx)
    
class LogResponse(LogSchema):
    log_id: str # Firestore Document ID (log_xxx)
