from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from datetime import datetime
from typing import Optional

class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel
        populate_by_name = True

class WatchChannelSchema(CamelModel):
    channel_id: str = Field(..., description="채널 식별을 위한 고유 UUID")
    resource_id: str = Field(..., description="Google Drive API가 반환한 리소스 ID")
    user_email: str = Field(..., description="이 채널을 소유한 사용자의 이메일")
    user_uid: str = Field(..., description="사용자의 UID")
    webhook_url: str = Field(..., description="알림을 수신할 Webhook URL")
    expiration: Optional[int] = Field(None, description="채널 만료 시간 (Unix Timestamp ms)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="채널 생성 일시")

    class Config:
        json_schema_extra = {
            "example": {
                "channel_id": "123e4567-e89b-12d3-a456-426614174000",
                "resource_id": "wDyM...",
                "user_email": "user@example.com",
                "user_uid": "user_123",
                "webhook_url": "https://api.omnihub.com/webhook/drive",
                "expiration": 1735689600000
            }
        }
