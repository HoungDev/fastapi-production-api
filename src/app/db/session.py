from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

database_url = make_url(settings.DATABASE_URL)
connect_args = (
    {"options": "-c timezone=UTC"}
    if database_url.get_backend_name() == "postgresql"
    else {}
)

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
