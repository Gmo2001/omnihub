from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
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

        # 로그인 시간 및 토큰 업데이트
        update_data = {
            "last_login_at": datetime.now(),
            "photo_url": picture,
            "display_name": name,
            "google_access_token": access_token_google,
            "role": final_role 
        }
        if refresh_token_google:
            update_data["google_refresh_token"] = refresh_token_google
            
        user_ref.update(update_data)
    else:
        # 신규 유저 생성
        # Super Admin Check
        if settings.SUPER_ADMIN_EMAIL and email == settings.SUPER_ADMIN_EMAIL:
            final_role = "admin"

        new_user = UserSchema(
            uid=str(email), # 내부 관리용 UID도 이메일로 통일하거나 Google UID 사용
            email=email,
            display_name=name,
            photo_url=picture,
            department="Unknown", 
            department_id="UNKNOWN",
            role=final_role,
            google_access_token=access_token_google,
            google_refresh_token=refresh_token_google
        )
        user_ref.set(new_user.dict())
        
    # [LogService] 로그인 활동 기록
    # current_user 객체를 구성해야 함 (DB에서 막 가져온 데이터 기반)
    current_user_obj = UserSchema(**user_ref.get().to_dict())
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

# JWT 생성 유틸리티
# 구글 토큰은 구글 꺼니까, 우리 시스템 전용 "출입증"을 새로 만들어줍니다.
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60*24) # 24시간 유효
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
