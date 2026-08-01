from app.schemas import UserCreate


class UserRepository:
    def create(self, user: UserCreate):
        return user