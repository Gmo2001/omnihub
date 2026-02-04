from fastapi import APIRouter, Depends, HTTPException, status
from app.core.dependencies import get_current_user
from app.models.user import UserSchema
from app.core.gcp_clients import get_firestore_client
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
    position: Optional[str] = None
    role: Optional[str] = None

@router.get("/users", response_model=List[UserSchema])
async def read_users(
    skip: int = 0, 
    limit: int = 100, 
    current_user: UserSchema = Depends(get_current_admin_user)
):
    users_ref = get_firestore_client().collection("users").limit(limit).offset(skip)
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
    user_ref = get_firestore_client().collection("users").document(email)
    doc = user_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = user_update.dict(exclude_unset=True)
    if not update_data:
        return UserSchema(**doc.to_dict()) # No changes
        
    user_ref.update(update_data)
    
    updated_doc = user_ref.get()
    return UserSchema(**updated_doc.to_dict())

@router.get("/test-bigquery")
async def test_bigquery_connection(
    current_user: UserSchema = Depends(get_current_admin_user)
):
    """
    [Diagnostic] Force-test BigQuery connection and return result.
    """
    report = {"status": "starting", "details": []}
    
    try:
        client = get_bq_client()
        report["details"].append(f"Client Init: Success (Project: {client.project})")
        
        # 1. Check Dataset
        dataset_ref = client.dataset(DATASET_ID)
        try:
            client.get_dataset(dataset_ref)
            report["details"].append(f"Dataset '{DATASET_ID}': Found ✅")
        except Exception as e:
            report["status"] = "failed"
            report["details"].append(f"Dataset '{DATASET_ID}': Not Found/Error ❌ ({str(e)})")
            return report
            
        # 2. Check Table
        table_ref = dataset_ref.table(LOGS_TABLE)
        try:
            client.get_table(table_ref)
            report["details"].append(f"Table '{LOGS_TABLE}': Found ✅")
        except Exception as e:
            report["details"].append(f"Table '{LOGS_TABLE}': Not Found ⚠️ ({str(e)})")
            # Proceed to try insert anyway, maybe logic handles creation? 
            # Actually our logic handles creation, but let's see.
        
        # 3. Dry Run Insert
        row = {
            "timestamp": datetime.utcnow().isoformat(),
            "document_id": f"TEST_LOG_{uuid.uuid4()}", 
            "operation": "TEST_INSERT",
            "data": "{\"message\": \"This is a diagnostic test log\"}" 
        }
        
        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            report["status"] = "failed"
            report["details"].append(f"Insert Test: Failed ❌ {errors}")
        else:
            report["status"] = "success"
            report["details"].append("Insert Test: Success 🎉")
            
    except Exception as e:
        report["status"] = "error"
        report["details"].append(f"Unexpected Error: {str(e)}")
        
    return report
