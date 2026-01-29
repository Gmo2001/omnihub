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

# 2. 로그인 URL (Frontend -> Backend -> Google)
@router.get("/auth/login")
async def login(request: Request, force_consent: bool = False):
    # redirect_uri는 Google Console에 등록한 주소와 정확히 일치해야 함
    # Cloud Run은 Load Balancer 뒤에 있어서 request.url_for가 'http'를 반환할 수 있음
    # 따라서 강제로 https로 변환하거나 ProxyHeadersMiddleware를 써야 하지만, 
    # 여기서는 안전하게 문자열 치환으로 처리
    redirect_uri = str(request.url_for('auth_callback'))
    if "omnihub-backend" in redirect_uri and "run.app" in redirect_uri:
        redirect_uri = redirect_uri.replace("http://", "https://")
        
    # access_type='offline' is required to get a refresh_token
    # prompt='consent' forces the consent screen to ensure we get a refresh_token
    kwargs = {'access_type': 'offline'}
    if force_consent:
        kwargs['prompt'] = 'consent'
        
    return await oauth.google.authorize_redirect(
        request, redirect_uri, **kwargs
    )


# 3. 콜백 처리 (Google -> Backend)
@router.get("/auth/callback")
async def auth_callback(request: Request, background_tasks: BackgroundTasks):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth Error: {str(e)}")
    
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    # 4. 사용자 정보 추출
    uid = user_info.get('sub') # Google Unique ID
    email = user_info.get('email')
    name = user_info.get('name')
    picture = user_info.get('picture')

    # Google Tokens
    access_token_google = token.get('access_token')
    refresh_token_google = token.get('refresh_token')

    # 5. Firestore 업데이트 (Upsert)
    user_ref = db.collection('users').document(str(email)) # 이메일을 Key로 사용 (간편함)
    
    # 기존 유저 확인
    existing_user_snapshot = user_ref.get()
    
    # 최종 Role 결정
    final_role = "user"

    if existing_user_snapshot.exists:
        existing_data = existing_user_snapshot.to_dict()
        final_role = existing_data.get('role', 'user')
        
        # Super Admin Check (Always Promote)
        if settings.SUPER_ADMIN_EMAIL and email == settings.SUPER_ADMIN_EMAIL:
            final_role = "admin"

        # 로그인 시간 및 토큰 업데이트 (CamelCase keys)
        update_data = {
            "lastLoginAt": datetime.now(),
            "photoUrl": picture,
            "displayName": name,
            "googleAccessToken": access_token_google,
            "role": final_role 
        }
        if refresh_token_google:
            update_data["googleRefreshToken"] = refresh_token_google
            
        user_ref.update(update_data)
    else:
        # 신규 유저 생성
        # Super Admin Check
        if settings.SUPER_ADMIN_EMAIL and email == settings.SUPER_ADMIN_EMAIL:
            final_role = "admin"

        new_user = UserSchema(
            userId=to_internal_id('usr_', str(email)), # uid -> userId (Prefix 적용)
            email=email,
            display_name=name,
            photo_url=picture,
            department="Unknown", 
            department_id="UNKNOWN",
            role=final_role,
            google_access_token=access_token_google,
            google_refresh_token=refresh_token_google
        )
        # [Fix] CamelCase Enforcement
        user_ref.set(new_user.dict(by_alias=True))
        
    # [LogService] 로그인 활동 기록
    # current_user 객체를 구성해야 함 (DB에서 막 가져온 데이터 기반)
    # DB에는 camelCase로 저장되어 있을 수 있음 -> UserSchema는 alias로 처리하므로 호환됨
    user_data = user_ref.get().to_dict()
    current_user_obj = UserSchema(**user_data)
    log_user_action(
        user=current_user_obj,
        action=ActionType.VIEW, # 로그인 == 조회
        file_id="auth",
        success=True,
        details={"method": "google_oauth"}
    )

    # [Auto-Watch] 백그라운드 작업으로 감시 등록 실행
    # Base URL 추출 (Cloud Run의 HTTPS 프로토콜 처리)
    base_url = str(request.base_url)
    if "omnihub-backend" in base_url and "run.app" in base_url:
        base_url = base_url.replace("http://", "https://")
    
    background_tasks.add_task(register_user_watch, current_user_obj, base_url)

    # 6. 자체 JWT 토큰 발급 (Frontend에게 줄 출입증)
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


from google_auth_oauthlib.flow import Flow

class GoogleAuthCode(BaseModel):
    code: str

# 7. Frontend Code Exchange (Offline Access Support)
@router.post("/auth/google")
async def exchange_auth_code(data: GoogleAuthCode, background_tasks: BackgroundTasks):
    try:
        # 1. Create Flow
        # Note: server_metadata_url is not directly supported in all Flow constructors easily via dict, 
        # but client_config works. We use the settings.
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
        
        # 2. Exchange Code for Credentials (Access + Refresh Token)
        flow.fetch_token(code=data.code)
        credentials = flow.credentials
        
        # 3. Get User Info from ID Token (included in credentials)
        # credentials.id_token contains the JWT with user info
        if not credentials.id_token:
             # Fallback: Fetch from userinfo endpoint if id_token is missing (rare but possible)
             session = flow.authorized_session()
             user_info = session.get('https://www.googleapis.com/userinfo/v2/me').json()
             email = user_info.get('email')
             uid = user_info.get('id')
             name = user_info.get('name')
             picture = user_info.get('picture')
        else:
             import json
             import base64
             # Basic decode without verify (verify done by fetch_token ideally, or use id_token.verify_token)
             # simpler: use id_token verifier correctly
             from google.oauth2 import id_token
             from google.auth.transport import requests as google_requests
             
             id_info = id_token.verify_oauth2_token(
                credentials.id_token, 
                google_requests.Request(), 
                settings.GOOGLE_CLIENT_ID
             )
             email = id_info.get('email')
             uid = id_info.get('sub')
             name = id_info.get('name')
             picture = id_info.get('picture')

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Code Exchange Failed: {str(e)}")

    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve email")

    # --- User Upsert Logic ---
    user_ref = db.collection('users').document(str(email))
    existing_user_snapshot = user_ref.get()
    
    final_role = "user"

    if existing_user_snapshot.exists:
        existing_data = existing_user_snapshot.to_dict()
        final_role = existing_data.get('role', 'user')
        
        if settings.SUPER_ADMIN_EMAIL and email == settings.SUPER_ADMIN_EMAIL:
            final_role = "admin"

        update_data = {
            "lastLoginAt": datetime.now(),
            "photoUrl": picture,
            "displayName": name,
            "role": final_role,
            "googleAccessToken": credentials.token
        }
        if credentials.refresh_token:
            update_data["googleRefreshToken"] = credentials.refresh_token
            
        user_ref.update(update_data)
    else:
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
            google_access_token=credentials.token,
            google_refresh_token=credentials.refresh_token
        )
        user_ref.set(new_user.dict(by_alias=True))
    
    # Log Action
    user_data = user_ref.get().to_dict()
    current_user_obj = UserSchema(**user_data)
    log_user_action(
        user=current_user_obj,
        action=ActionType.VIEW,
        file_id="auth",
        success=True,
        details={"method": "google_code_flow"}
    )
    
    # Auto-Watch
    background_tasks.add_task(register_user_watch, current_user_obj, "https://omnihub-backend-707724932002.asia-northeast3.run.app")

    # Issue JWT
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

# JWT 생성 유틸리티
# 구글 토큰은 구글 꺼니까, 우리 시스템 전용 "출입증"을 새로 만들어줍니다.
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60*24) # 24시간 유효
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
