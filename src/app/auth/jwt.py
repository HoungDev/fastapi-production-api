from datetime import datetime, timedelta, UTC
import os

import jwt
from dotenv import load_dotenv


load_dotenv()


SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key",
)

ALGORITHM = os.getenv(
    "ALGORITHM",
    "HS256",
)

JWT_AUDIENCE = os.getenv(
    "JWT_AUDIENCE",
    "fastapi-client",
)

JWT_ISSUER = os.getenv(
    "JWT_ISSUER",
    "fastapi-production-api",
)

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "30",
    )
)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    to_encode.update({
    "aud": JWT_AUDIENCE,
    "iss": JWT_ISSUER,
})

    expire = datetime.now(UTC) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )