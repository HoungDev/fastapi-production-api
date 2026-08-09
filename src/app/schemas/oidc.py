from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ExternalIdentityResponse(BaseModel):
    id: int
    issuer: str
    email: str | None
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OIDCLinkResponse(BaseModel):
    linked: Literal[True] = True
    identity: ExternalIdentityResponse


class OIDCMessageResponse(BaseModel):
    message: str
