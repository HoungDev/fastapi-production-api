from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class UserCreate(BaseModel):
    username: str
    password: str
    email: EmailStr | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().casefold() if value is not None else None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    email: str | None = None
    email_verified_at: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserRoleUpdate(BaseModel):
    role: str


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserAdminResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    model_config = ConfigDict(
        from_attributes=True,
    )
