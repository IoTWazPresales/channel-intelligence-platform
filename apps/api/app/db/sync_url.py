"""Normalize Postgres URLs for synchronous SQLAlchemy engines (psycopg v3)."""

from __future__ import annotations

import logging
import socket
from urllib.parse import unquote, urlparse, urlunparse

from app.core.config import Settings

logger = logging.getLogger(__name__)


def sqlalchemy_sync_engine_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _normalize_pg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def supabase_direct_primary_sync_url(pooler_sync_url: str) -> str | None:
    """Rewrite Supabase **session pooler** sync URL to direct primary ``db.<ref>.supabase.co:5432``.

    Returns ``None`` when the URL is not a Supabase pooler host or project ref cannot be parsed.
    """
    normalized = _normalize_pg_url(pooler_sync_url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if "pooler.supabase.com" not in host:
        return None
    user = unquote(parsed.username or "")
    ref = ""
    if user.startswith("postgres.") and "." in user:
        ref = user.split(".", 1)[1]
    if not ref:
        return None
    port = parsed.port or 5432
    if int(port) != 5432:
        return None
    direct_host = f"db.{ref}.supabase.co"
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"{netloc.split('@', 1)[0]}@{direct_host}:{port}"
    else:
        netloc = f"{direct_host}:{port}"
    return urlunparse(
        (
            "postgresql",
            netloc,
            parsed.path or "/postgres",
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def pg_host_resolvable(url: str) -> bool:
    """True when the URL host resolves for psycopg (IPv4 and/or IPv6 on this machine)."""
    parsed = urlparse(_normalize_pg_url(url))
    host = parsed.hostname
    if not host or host in {"localhost", "127.0.0.1"}:
        return True
    port = int(parsed.port or 5432)
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


def resolve_sync_engine_url(settings: Settings) -> str:
    """URL for Celery / batch sync engine — prefer explicit writable primary over pooler."""
    if settings.database_url_sync_writable:
        return sqlalchemy_sync_engine_url(settings.database_url_sync_writable)
    raw = settings.database_url_sync
    if settings.cip_supabase_sync_direct_primary:
        direct = supabase_direct_primary_sync_url(raw)
        if direct and pg_host_resolvable(direct):
            return sqlalchemy_sync_engine_url(direct)
        if direct:
            logger.warning(
                "Supabase direct primary host %s is not resolvable on this machine; "
                "keeping pooler DATABASE_URL_SYNC for sync engine. "
                "Set DATABASE_URL_SYNC_WRITABLE or CIP_SUPABASE_SYNC_DIRECT_PRIMARY=false to silence.",
                urlparse(_normalize_pg_url(direct)).hostname,
            )
    return sqlalchemy_sync_engine_url(raw)

