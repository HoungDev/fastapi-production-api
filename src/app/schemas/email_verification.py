from pydantic import BaseModel, EmailStr, Field, field_validator


class EmailVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().casefold()


class EmailVerificationConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class EmailVerificationAccepted(BaseModel):
    message: str
