"""Synchronous session for Alembic migrations and Celery tasks."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

settings = get_settings()

# TCP keepalives detect dead pooler sockets during long DSI validate cache reads.
# keepalives_count is ignored on Windows; idle/interval still apply.
_SYNC_CONNECT_ARGS = {
    "prepare_threshold": None,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

sync_engine = create_engine(
    sqlalchemy_sync_engine_url(settings.database_url_sync),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args=_SYNC_CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=sync_engine, class_=Session, autoflush=False, autocommit=False)


def get_sync_session() -> Session:
    return SessionLocal()
