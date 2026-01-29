import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional

def log_system_event(
    event_type: str,
    component: str,
    payload: Dict[str, Any],
    severity: str = "INFO"
):
    """
    [Pipeline B] 시스템 이벤트를 구조화된 JSON으로 표준 출력(Stdout)에 기록합니다.
    GCP Log Router가 이를 감지하여 BigQuery 'system_logs' 테이블로 라우팅합니다.
    
    Args:
        event_type (str): 이벤트 식별자 (예: AI_ANALYSIS_COMPLETED, FILE_DETECTED)
        component (str): 발생 모듈명 (예: AIService, Webhook)
        payload (dict): 이벤트별 상세 데이터 (BigQuery JSON 컬럼에 저장됨)
        severity (str): 로그 레벨 (INFO, ERROR, WARNING)
    """
    try:
        log_entry = {
            "event_type": event_type,
            "severity": severity,
            "component": component,
            "timestamp": datetime.utcnow().isoformat() + "Z", # ISO 8601
            "payload": payload,
            # Cloud Logging Special Fields for better UI integration
            "message": f"[{component}] {event_type}", 
        }
        
        # JSON Serialize & Print to Stdout (Thread-safe in simple usage)
        print(json.dumps(log_entry))
        
        # Flush stdout to ensure instant visibility in logs
        sys.stdout.flush()
        
    except Exception as e:
        # JSON 직렬화 실패 등의 경우 Fallback
        print(f"ERROR: Failed to log system event: {e}")
