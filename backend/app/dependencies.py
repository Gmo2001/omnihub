from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import settings
from app.core.gcp_clients import db
from app.models.user import UserSchema

# [Fix] OAuth2PasswordBearer -> HTTPBearer (Token Paste Mode)
# Google OAuth는 브라우저에서 토큰을 복사해오므로, Swagger UI에 단순 붙여넣기 기능이 필요함
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserSchema:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 1. 토큰 디코딩
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # 2. DB에서 유저 조회 (Real DB Check)
    user_ref = db.collection("users").document(email).get()
    
    if not user_ref.exists:
        raise credentials_exception
        
    # 3. User 객체 반환
    user_data = user_ref.to_dict()
    return UserSchema(**user_data)
