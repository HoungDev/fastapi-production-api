from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MFAPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=72)


class MFAEnrollmentResponse(BaseModel):
    secret: str
    provisioning_uri: str
    expires_at: datetime


class MFACodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MFARegenerateRequest(MFACodeRequest, MFAPasswordRequest):
    pass


class MFADisableRequest(MFARegenerateRequest):
    pass


class MFARecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class MFAStatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


class MFAChallengeResponse(BaseModel):
    mfa_required: Literal[True] = True
    challenge_token: str
    expires_in: int


class MFAVerifyChallengeRequest(MFACodeRequest):
    challenge_token: str = Field(min_length=32, max_length=512)


class MFAMessageResponse(BaseModel):
    message: str
