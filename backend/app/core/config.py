from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "OmniHub"
    PROJECT_ID: str    #외부에서 설정(cloud run)
    
    # Default to service_account.json in the backend root if not set in env
    GOOGLE_APPLICATION_CREDENTIALS: str = "service_account.json"  # Google Cloud Credentials
    
    # OAuth 2.0 (From Google Cloud Console)
    GOOGLE_CLIENT_ID: str = "" 
    GOOGLE_CLIENT_SECRET: str = ""
    SECRET_KEY: str = "" # For signing internal JWT
    ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
