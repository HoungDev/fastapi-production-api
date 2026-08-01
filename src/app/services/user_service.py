from app.repositories.user_repository import UserRepository
from app.schemas import UserCreate


class UserService:
    def __init__(self):
        self.repository = UserRepository()

    def create_user(self, user: UserCreate):
        return self.repository.create(user)
from app.auth.security import hash_password    