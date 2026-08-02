from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.me import router as me_router
from app.api.v1.users import router as users_router
from app.auth.login import router as login_router
from app.auth.register import router as register_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.exceptions.handlers import register_exception_handlers
from app.middlewares.cors import setup_cors


setup_logging()

app = FastAPI(title=settings.APP_NAME)


setup_cors(app)
register_exception_handlers(app)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(login_router)
app.include_router(register_router)
app.include_router(me_router)
app.include_router(auth_router)


@app.get("/")
def root():
    return {"message": "FastAPI Production API is running!"}