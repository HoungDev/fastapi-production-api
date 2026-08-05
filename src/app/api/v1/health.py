from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine


router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "ok",
    }


@router.get("/health/db")
def database_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as error:
        return {
            "status": "error",
            "database": "disconnected",
            "detail": str(error),
        }