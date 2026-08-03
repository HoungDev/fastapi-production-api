from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserRoleUpdate(BaseModel):
    role: str


class UserAdminResponse(BaseModel):
    id: int
    username: str
    role: str

    model_config = ConfigDict(
        from_attributes=True,
    )