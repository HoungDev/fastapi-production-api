from fastapi import FastAPI

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.email_verification import router as email_verification_router
from app.api.v1.health import router as health_router
from app.api.v1.me import router as me_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.mfa import router as mfa_router
from app.api.v1.oidc import router as oidc_router
from app.api.v1.password_reset import router as password_reset_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.users import router as users_router
from app.auth.login import router as login_router
from app.auth.register import router as register_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.exceptions.handlers import register_exception_handlers
from app.middlewares.cors import setup_cors
from app.middlewares.rate_limit import setup_rate_limit
from app.middlewares.request_logging import setup_request_logging
from app.middlewares.security_headers import setup_security_headers
from fastapi_production_api import __version__

setup_logging()


app = FastAPI(
    title=settings.APP_NAME,
    description="""
FastAPI Production API

Security-focused backend foundation with:

- JWT Authentication
- Refresh Token Authentication
- Role Based Access Control
- PostgreSQL Database
- Alembic Database Migration
- Automated Testing
- GitHub Actions CI Pipeline
""",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


setup_cors(app)

setup_security_headers(app)

setup_rate_limit(app)

setup_request_logging(app)

register_exception_handlers(app)


app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(users_router)
app.include_router(login_router)
app.include_router(register_router)
app.include_router(auth_router)
app.include_router(email_verification_router)
app.include_router(password_reset_router)
app.include_router(mfa_router)
app.include_router(oidc_router)
app.include_router(sessions_router)
app.include_router(me_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {
        "message": "FastAPI Production API is running!",
        "version": __version__,
    }
