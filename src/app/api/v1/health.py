import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()
logger = logging.getLogger("fastapi-production-api.health")


def _database_is_ready() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("database_readiness_check_failed", exc_info=True)
        return False


@router.get("/health/live")
def liveness_check():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check():
    if _database_is_ready():
        return {
            "status": "ok",
            "checks": {"database": "ok"},
        }

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "error",
            "checks": {"database": "unavailable"},
        },
    )


@router.get("/health", deprecated=True)
def health_check():
    return liveness_check()


@router.get("/health/db", deprecated=True)
def database_health_check():
    if _database_is_ready():
        return {
            "status": "ok",
            "database": "connected",
        }

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "error",
            "database": "disconnected",
        },
    )
