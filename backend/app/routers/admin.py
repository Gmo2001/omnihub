from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user
from app.models.user import UserSchema
from app.core.gcp_clients import db
from typing import List, Optional
from pydantic import BaseModel

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
