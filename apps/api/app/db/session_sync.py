"""Synchronous session for Alembic migrations and Celery tasks."""

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.sync_url import resolve_sync_engine_url

settings = get_settings()


def build_sync_connect_args(settings: Settings) -> dict[str, Any]:
    """psycopg v3 connect_args for the sync engine.

    TCP keepalives detect dead pooler sockets during long DSI validate cache reads
    (keepalives_count is ignored on Windows; idle/interval still apply). The libpq
    ``options`` string adds server-side timeouts — chiefly ``idle_in_transaction_session_timeout``
    — so a connection stuck idle-in-transaction (the DSI validate hang) is terminated and the
    next use raises a transient error the upfront-cache retry wrapper recovers from, rather
    than blocking forever on a half-dead socket.
    """
    args: dict[str, Any] = {
        "prepare_threshold": None,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    option_parts: list[str] = []
    idle_ms = int(getattr(settings, "cip_sync_idle_in_transaction_timeout_ms", 0) or 0)
    if idle_ms > 0:
        option_parts.append(f"-c idle_in_transaction_session_timeout={idle_ms}")
    stmt_ms = int(getattr(settings, "cip_sync_statement_timeout_ms", 0) or 0)
    if stmt_ms > 0:
        option_parts.append(f"-c statement_timeout={stmt_ms}")
    if option_parts:
        args["options"] = " ".join(option_parts)
    return args


_SYNC_CONNECT_ARGS = build_sync_connect_args(settings)

sync_engine = create_engine(
    resolve_sync_engine_url(settings),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args=_SYNC_CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=sync_engine, class_=Session, autoflush=False, autocommit=False)


def get_sync_session() -> Session:
    return SessionLocal()
