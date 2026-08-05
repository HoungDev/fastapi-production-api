from app.db.session import SessionLocal
from app.models.user import User
from app.auth.security import hash_password


def pytest_configure():
    db = SessionLocal()

    user = db.query(User).filter(
        User.username == "houngdev"
    ).first()

    if not user:
        user = User(
            username="houngdev",
            password=hash_password("secret123"),
            role="admin",
        )

        db.add(user)
        db.commit()

    db.close()