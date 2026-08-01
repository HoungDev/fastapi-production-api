from fastapi import FastAPI
from app.api.v1.health import router as health_router
from app.core.config import settings
app = FastAPI(title=settings.APP_NAME)
app.include_router(health_router)
@app.get("/")
def root():
    return {"message": "FastAPI Production API is running!"}
