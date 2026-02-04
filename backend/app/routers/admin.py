from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user
from app.models.user import UserSchema
from app.core.gcp_clients import db
from typing import List, Optional
from pydantic import BaseModel
from app.services.bq_service import get_bq_client, DATASET_ID, LOGS_TABLE
from datetime import datetime
import uuid

# admin api로 관리자만 접근해서 특정사용자의 부서 및 직책 정보를 수정할 수 있도록 함
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={404: {"description": "Not found"}},
)

def get_current_admin_user(current_user: UserSchema = Depends(get_current_user)) -> UserSchema:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges",
        )
    return current_user

class UserUpdate(BaseModel):
    department: Optional[str] = None
    department_id: Optional[str] = None # Enum Validation will happen at Service/UI level or implicit Pydantic if typed
    position: Optional[str] = None
    role: Optional[str] = None

@router.get("/users", response_model=List[UserSchema])
async def read_users(
    skip: int = 0, 
    limit: int = 100, 
    current_user: UserSchema = Depends(get_current_admin_user)
):
    users_ref = db.collection("users").limit(limit).offset(skip)
    docs = users_ref.stream()
    users = []
    for doc in docs:
        users.append(UserSchema(**doc.to_dict()))
    return users

@router.patch("/users/{email}", response_model=UserSchema)
async def update_user(
    email: str, 
    user_update: UserUpdate, 
    current_user: UserSchema = Depends(get_current_admin_user)
):
    user_ref = db.collection("users").document(email)
    doc = user_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = user_update.dict(exclude_unset=True)
    if not update_data:
        return UserSchema(**doc.to_dict()) # No changes
        
    user_ref.update(update_data)
    
    updated_doc = user_ref.get()
    return UserSchema(**updated_doc.to_dict())

@router.get("/system-health")
async def check_system_health(
    current_user: UserSchema = Depends(get_current_admin_user)
):
    """
    [Diagnostic] Check Firestore and BigQuery connection status.
    Returns specific error codes and messages for UI handling.
    """
    from app.utils.error_handler import classify_error
    
    report = {
        "firestore": {"status": "unknown", "latency_ms": 0},
        "bigquery": {"status": "unknown", "latency_ms": 0},
        "details": []
    }
    
    # 1. Check Firestore
    try:
        start_fs = datetime.now()
        # Perform a lightweight read
        db.collection("system_status").document("health_check").get()
        latency_fs = (datetime.now() - start_fs).total_seconds() * 1000
        
        report["firestore"] = {
            "status": "ok", 
            "latency_ms": round(latency_fs, 2)
        }
        report["details"].append(f"Firestore: Connected (Latency: {round(latency_fs, 2)}ms)")
    except Exception as e:
         err_info = classify_error(e, "Firestore")
         report["firestore"] = err_info
         report["details"].append(f"Firestore: {err_info['message']}")

    # 2. Check BigQuery
    try:
        start_bq = datetime.now()
        client = get_bq_client()
        # Lightweight check: get dataset metadata
        dataset_ref = client.dataset(DATASET_ID)
        client.get_dataset(dataset_ref)
        latency_bq = (datetime.now() - start_bq).total_seconds() * 1000
        
        report["bigquery"] = {
            "status": "ok", 
            "latency_ms": round(latency_bq, 2)
        }
        report["details"].append(f"BigQuery: Connected (Latency: {round(latency_bq, 2)}ms)")
    except Exception as e:
        err_info = classify_error(e, "BigQuery")
        report["bigquery"] = err_info
        report["details"].append(f"BigQuery: {err_info['message']}")
        
    return report

@router.get("/system-errors")
async def get_system_errors(
    limit: int = 50,
    current_user: UserSchema = Depends(get_current_admin_user)
):
    """
    [Log Viewer] Retrieve system error logs from Firestore (Today Only).
    Used for AI-B dashboard or Admin Console analysis.
    """
    try:
        # Query: sys_errors/{today}/logs collection, sort by timestamp desc
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        
        errors_ref = db.collection("sys_errors").document(today_str).collection("logs").order_by(
            "timestamp", direction=firestore.Query.DESCENDING
        ).limit(limit)
        
        docs = errors_ref.stream()
        error_logs = []
        
        for doc in docs:
            data = doc.to_dict()
            # Convert timestamp to ISO format for JSON
            if data.get("timestamp"):
                data["timestamp"] = data["timestamp"].isoformat()
            data["id"] = doc.id
            error_logs.append(data)
            
        return error_logs
        
    except Exception as e:
        # If index is missing for sorting, fallback to simple get
        print(f"[Admin] Error fetching system errors: {e}")
        from app.utils.error_handler import raise_classified_http_exception
        raise_classified_http_exception(e, "Admin Log Viewer", "admin")
