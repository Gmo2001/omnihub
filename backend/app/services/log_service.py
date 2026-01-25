from datetime import datetime
from typing import Optional, Dict, Any
from app.core.gcp_clients import db
from app.models.user import UserSchema

# Collection Name
LOGS_COLLECTION = "logs"

def log_activity(
    user: UserSchema,
    action: str,
    resource: str,
    details: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
):
    """
    사용자 활동 로그를 Firestore에 적재합니다.
    이 데이터는 Firebase Extension을 통해 BigQuery로 실시간 동기화됩니다.
    
    Args:
        user: 활동을 수행한 사용자 객체
        action: 수행한 작업 (예: "login", "ingest_file", "process_docai")
        resource: 대상 리소스 (예: "auth", "file:12345")
        details: 추가 상세 정보 (JSON)
        level: 로그 레벨 (INFO, WARN, ERROR)
    """
    # Action Code Mapping (AI-B Requirement)
    action_map = {
        "view": 0,
        "download": 1,
        "move": 2,
        "approve": 3,
        "reject": 3,
        "denied": 4
    }
    action_code = action_map.get(action, 99) # 99: Unknown

    try:
        log_entry = {
            "timestamp": datetime.utcnow(), # BigQuery Partitioning 기준
            "user_id": user.uid,
            "user_email": user.email,
            "department": user.department or "Unknown",
            "user_department_id": user.department_id, # AI-B Analysis
            "action": action,
            "action_code": action_code, # AI-B Analysis (Int)
            "resource": resource,
            "level": level,
            "success": details.get("success", False) if details else True, # Default True, but overridable
            "details": details or {}
        }
        
        # Add to Firestore (Auto-ID)
        db.collection(LOGS_COLLECTION).add(log_entry)
        
    except Exception as e:
        # 로그 적재 실패가 메인 로직을 방해하면 안 됨 -> 콘솔 출력만
        print(f"[LogService Error] Failed to write log: {e}")
