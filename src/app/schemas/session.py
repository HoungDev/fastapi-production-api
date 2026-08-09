from datetime import datetime

from pydantic import BaseModel


class DeviceSession(BaseModel):
    id: str
    device_name: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime


class SessionRevocationResponse(BaseModel):
    message: str
