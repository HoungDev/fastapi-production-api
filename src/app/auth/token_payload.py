from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    sub: str
    amr: list[str] = Field(default_factory=list)
    auth_time: int | None = None
