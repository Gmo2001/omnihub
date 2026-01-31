from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.utils.id_utils import to_internal_id
from authlib.integrations.starlette_client import OAuth
from app.core.config import settings
from app.core.gcp_clients import db
from app.models.user import UserSchema
from datetime import datetime, timedelta
from app.services.log_service import log_user_action
from app.models.log import ActionType
from app.services.drive_service import register_user_watch
from jose import jwt
from passlib.context import CryptContext
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel

import os
# Google Scope 변경(확장)으로 인한 에러 방지 (email -> https://.../userinfo.email)
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

router = APIRouter(tags=["auth"])

# 1. OAuth 설정
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/drive.readonly' 
    }
)

# --- Helper: User Sync Logic (Common) ---
def sync_google_user_to_db(email: str, name: str, picture: str, access_token: str, refresh_token: str = None) -> tuple[str, UserSchema]:
    """
    어떤 경로로 들어왔든, 구글 정보를 받아서
    Firestore 'users' 컬렉션에 저장(Upsert)하는 공통 함수입니다.
    """
    user_ref = db.collection('users').document(str(email))
    existing_user_snapshot = user_ref.get()
    
    final_role = "user"

    # 기본 업데이트 데이터
    common_data = {
        "lastLoginAt": datetime.now(),
        "photoUrl": picture,
        "displayName": name,
        "googleAccessToken": access_token
    }
    if refresh_token:
        common_data["googleRefreshToken"] = refresh_token

    if existing_user_snapshot.exists:
        existing_data = existing_user_snapshot.to_dict()
        final_role = existing_data.get('role', 'user')
        
        # Super Admin Check
        if settings.SUPER_ADMIN_EMAIL and email == settings.SUPER_ADMIN_EMAIL:
            final_role = "admin"

        update_data = {**common_data, "role": final_role}
        user_ref.update(update_data)
        
        # 최신 객체 구성을 위해 병합
        user_data = {**existing_data, **update_data}
    else:
        # 신규 생성
        if settings.SUPER_ADMIN_EMAIL and email == settings.SUPER_ADMIN_EMAIL:
            final_role = "admin"

        new_user = UserSchema(
            userId=to_internal_id('usr_', str(email)),
            email=email,
            display_name=name,
            photo_url=picture,
            department="Unknown", 
            department_id="UNKNOWN",
            role=final_role,
            google_access_token=access_token,
            google_refresh_token=refresh_token
        )
        user_ref.set(new_user.dict(by_alias=True))
        user_data = new_user.dict(by_alias=True)

    return final_role, UserSchema(**user_data)


# JWT 생성 유틸리티
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60*24) # 24시간 유효
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


# 2. [DEBUG/TEST ONLY] 서버 리다이렉트 방식 (Swagger에서 숨김 처리)
# 실제 React 앱에서는 사용하지 않으며, 백엔드 단독 테스트용으로 남겨둡니다.
@router.get("/auth/login", include_in_schema=False)
async def login(request: Request, force_consent: bool = False):
    redirect_uri = str(request.url_for('auth_callback'))
    if "omnihub-backend" in redirect_uri and "run.app" in redirect_uri:
        redirect_uri = redirect_uri.replace("http://", "https://")
        
    kwargs = {'access_type': 'offline'}
    if force_consent:
        kwargs['prompt'] = 'consent'
        
    return await oauth.google.authorize_redirect(
        request, redirect_uri, **kwargs
    )


@router.get("/auth/callback", include_in_schema=False)
async def auth_callback(request: Request, background_tasks: BackgroundTasks):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth Error: {str(e)}")
    
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    # 정보 추출
    email = user_info.get('email')
    name = user_info.get('name')
    picture = user_info.get('picture')
    access_token_google = token.get('access_token')
    refresh_token_google = token.get('refresh_token')

    # 공통 로직 호출
    final_role, current_user_obj = sync_google_user_to_db(
        email, name, picture, access_token_google, refresh_token_google
    )

    # 로그 기록
    log_user_action(
        user=current_user_obj,
        action=ActionType.LOGIN,
        file_id="auth",
        success=True,
        details={"method": "google_oauth_redirect"}
    )

    # Auto-Watch
    base_url = str(request.base_url)
    if "omnihub-backend" in base_url and "run.app" in base_url:
        base_url = base_url.replace("http://", "https://")
    background_tasks.add_task(register_user_watch, current_user_obj, base_url)

    # JWT 발급
    access_token = create_access_token(
        data={"sub": str(email), "email": email, "role": final_role}
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_info": {
            "email": email,
            "name": name,
            "picture": picture,
            "role": final_role
        }
    }


class GoogleAuthCode(BaseModel):
    code: str

# =================================================================
# 3. [ACTUAL SERVICE] 프론트엔드 코드 교환 (Main Production Flow)
# =================================================================
# React 프론트엔드에서 구글 로그인을 완료하고 받은 'Code'를 처리하는 진짜 입구입니다.
@router.post("/auth/google")
async def exchange_auth_code(data: GoogleAuthCode, background_tasks: BackgroundTasks):
    try:
        # 1. Create Flow
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=['openid', 'email', 'profile', 'https://www.googleapis.com/auth/drive.readonly']
        )
        
        # 'postmessage' is required for the React "Implicit" -> "Code" flow via popup
        flow.redirect_uri = 'postmessage'
        
        # 2. Exchange Code
        flow.fetch_token(code=data.code)
        credentials = flow.credentials
        
        # 3. Get User Info
        if not credentials.id_token:
             session = flow.authorized_session()
             user_info = session.get('https://www.googleapis.com/userinfo/v2/me').json()
             email = user_info.get('email')
             name = user_info.get('name')
             picture = user_info.get('picture')
        else:
             id_info = id_token.verify_oauth2_token(
                credentials.id_token, 
                google_requests.Request(), 
                settings.GOOGLE_CLIENT_ID
             )
             email = id_info.get('email')
             name = id_info.get('name')
             picture = id_info.get('picture')

    except Exception as e:
        import traceback
        print(f"CRITICAL AUTH FAILURE: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Code Exchange Failed: {str(e)}")

    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve email")

    # 공통 로직 호출
    final_role, current_user_obj = sync_google_user_to_db(
        email, name, picture, credentials.token, credentials.refresh_token
    )
    
    # 로그
    log_user_action(
        user=current_user_obj,
        action=ActionType.LOGIN,
        file_id="auth",
        success=True,
        details={"method": "google_code_flow"}
    )
    
    # Auto-Watch
    # 실제 서비스에서는 고정된 도메인이나 설정된 값을 사용
    background_tasks.add_task(register_user_watch, current_user_obj, "https://omnihub-backend-707724932002.asia-northeast3.run.app")

    # JWT 발급
    access_token = create_access_token(
        data={"sub": str(email), "email": email, "role": final_role}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_info": {
            "email": email,
            "name": name,
            "picture": picture,
            "role": final_role
        }
    }
