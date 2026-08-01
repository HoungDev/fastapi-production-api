from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str    