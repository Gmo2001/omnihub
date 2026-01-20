from datetime import datetime, timedelta
from typing import Optional
from app.models.log import LogSchema, ActionType
from app.core.gcp_clients import db 

class LogService:
    def create_log(
        self, 
        user_id: str, 
        file_id: str, 
        action: ActionType, 
        success: bool = True,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        로그를 생성하고 실제 Firestore에 저장합니다.
        (Synchronous method to be run in BackgroundTasks threadpool)
        """
        try:
            # 1. 메타데이터 조회 (Real DB Call)
            # 동기 호출이므로 BackgroundTasks에서 실행되어야 메인 스레드를 차단하지 않음
            user_ref = db.collection("users").document(user_id).get()
            file_ref = db.collection("files").document(file_id).get()
            
            user_dept = None
            file_dept = None
            
            if user_ref.exists:
                user_dept = user_ref.to_dict().get("department_id")
            
            if file_ref.exists:
                file_dept = file_ref.to_dict().get("department_id")
            
            # 2. 만료 시간 설정 (TTL: 1년)
            expire_at = datetime.now() + timedelta(days=365)
            
            # 3. 로그 객체 조립 (Snapshot Creation)
            new_log = LogSchema(
                timestamp=datetime.now(),
                expire_at=expire_at,
                action_type=action,
                success=success,
                
                # Who
                user_id=user_id,
                user_department_id=user_dept,
                
                # What
                file_id=file_id,
                file_department_id=file_dept,
                
                # Context
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # 4. 저장 (Save to DB)
            # 'logs' 컬렉션에 자동 ID로 문서 생성
            db.collection("logs").add(new_log.dict())
            
            print(f"📝 [LogService] Saved Log: {action.value} by {user_id} (Success: {success})")
            
        except Exception as e:
            # 로그 저장이 실패하더라도 메인 비즈니스 로직은 방해하지 않도록 예외 처리
            print(f"❌ [LogService] Failed to save log: {str(e)}")
