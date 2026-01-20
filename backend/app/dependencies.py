from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from app.core.config import settings
from app.core.gcp_clients import db
from app.models.user import UserSchema

# Token URL은 Frontend가 없으므로 지금은 단순히 형식만 맞춤
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserSchema:
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
