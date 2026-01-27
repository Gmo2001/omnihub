from pydantic import BaseModel, Field
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

# Firestore 'logs' 컬렉션 구조
class LogSchema(BaseModel):
    # ==========================================
    # 1. 이벤트 필수 정보 (Event Basics)
    # ==========================================
    timestamp: datetime = Field(default_factory=datetime.utcnow) # UTC Time
    
    action_type: int        # 0~4 (Int)
    success: bool = True    # 성공/실패 여부
    
    # ==========================================
    # 2. 주체 식별자 및 스냅샷 (Who)
    # ==========================================
    user_id: str            # 사용자 ID
    user_department_id: Optional[str] = None # [Snapshot] 당시 사용자의 부서 코드
    
    # ==========================================
    # 3. 객체 식별자 및 스냅샷 (What)
    # ==========================================
    file_id: str            # 파일 ID
    file_dept_id: Optional[str] = None # [Snapshot] 당시 파일의 소속 부서 코드
    
    # ==========================================
    # 4. 기타 메타데이터 (Context)
    # ==========================================
    ip_address: Optional[str] = None  # 접속 IP
    user_agent: Optional[str] = None  # 브라우저/기기 정보

class LogResponse(LogSchema):
    log_id: str # Firestore Document ID
