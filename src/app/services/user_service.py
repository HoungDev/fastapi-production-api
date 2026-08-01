from app.schemas import UserCreate


class UserService:
    def create_user(self, user: UserCreate):
        return user