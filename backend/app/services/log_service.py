from datetime import datetime
from typing import Optional, Dict, Any
from app.core.gcp_clients import db
from app.models.user import UserSchema
from app.models.log import LogSchema, ActionType

# Collection Name
LOGS_COLLECTION = "logs"

def log_user_action(
    user: UserSchema,
    action: ActionType,
    file_id: str,
    file_dept_id: Optional[str] = None,
    success: bool = True,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    [Pipeline A] 사용자 행동 로그를 Firestore에 적재합니다.
    Stream Firestore to BigQuery Extension을 통해 실시간으로 DW에 전송됩니다.
    """
    try:
        log_entry = LogSchema(
            timestamp=datetime.utcnow(),
            user_id=user.email, # BigQuery 분석용 식별자
            user_department_id=user.department_id,
            
            file_id=file_id,
            file_dept_id=file_dept_id,
            
            action_type=action.value, # Int
            success=success,
            
            ip_address=ip_address,
            details=details or {}
        )
        
        # Add to Firestore (Auto-ID)
        db.collection(LOGS_COLLECTION).add(log_entry.dict())
        
    except Exception as e:
        # 로그 적재 실패가 메인 비즈니스 로직을 중단시키면 안 됨
        print(f"❌ [LogService Error] Failed to write log: {e}")
        
    except Exception as e:
        # 로그 적재 실패가 메인 로직을 방해하면 안 됨 -> 콘솔 출력만
        print(f"[LogService Error] Failed to write log: {e}")
