import pytest

from app.auth.security import hash_password
from app.db.session import SessionLocal
from app.middlewares.rate_limit import rate_limiter
from app.models.user import User


@pytest.fixture(autouse=True)
def reset_process_local_rate_limiter():
    rate_limiter.requests.clear()
    yield
    rate_limiter.requests.clear()


def pytest_configure():
    db = SessionLocal()

    user = db.query(User).filter(User.username == "houngdev").first()

    if not user:
        user = User(
            username="houngdev",
            password=hash_password("secret123"),
            role="admin",
        )

        db.add(user)
        db.commit()

    db.close()
