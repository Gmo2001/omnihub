from datetime import datetime
from typing import Optional, Dict, Any
from app.core.gcp_clients import db
from app.models.user import UserSchema
from app.models.log import LogSchema, ActionType

from app.services.bq_service import stream_logs_to_bigquery # Added BQ Service

# Collection Name
LOGS_COLLECTION = "logs"

def log_user_action(
    user: UserSchema,
    action: ActionType,
    file_id: str,
    success: bool = True,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    [Pipeline A] 사용자 행동 로그를 Firestore 및 BigQuery에 적재합니다.
    """
    try:
        log_entry = LogSchema(
            # [Fix] Strict Schema for AI-B (Only designated fields)
            event_ts=datetime.utcnow(),
            
            user_id=user.user_id, 
            user_department_id=user.department_id,
            
            file_id=file_id,
            
            action_type=action.value # Int
        )
        
        # 1. Add to Firestore (Auto-ID)
        log_dict = log_entry.dict(by_alias=True)
        db.collection(LOGS_COLLECTION).add(log_dict)
        
        # 2. Add to BigQuery (Direct Stream)
        stream_logs_to_bigquery(log_dict)
        
    except Exception as e:
        # 로그 적재 실패가 메인 비즈니스 로직을 중단시키면 안 됨
        print(f"❌ [LogService Error] Failed to write log: {e}")
        
    except Exception as e:
        # 로그 적재 실패가 메인 로직을 방해하면 안 됨 -> 콘솔 출력만
        print(f"[LogService Error] Failed to write log: {e}")
