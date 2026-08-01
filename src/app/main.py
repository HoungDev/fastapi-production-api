from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.exceptions.handlers import register_exception_handlers
from app.middlewares.cors import setup_cors

app = FastAPI(title=settings.APP_NAME)

setup_cors(app)
register_exception_handlers(app)

app.include_router(health_router)
app.include_router(users_router)


@app.get("/")
def root():
    return {"message": "FastAPI Production API is running!"}