"""Synchronous session for Alembic migrations and Celery tasks."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

settings = get_settings()
sync_engine = create_engine(sqlalchemy_sync_engine_url(settings.database_url_sync), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=sync_engine, class_=Session, autoflush=False, autocommit=False)


def get_sync_session() -> Session:
    return SessionLocal()
