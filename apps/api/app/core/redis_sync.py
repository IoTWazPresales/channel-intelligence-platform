"""Synchronous Redis client for lightweight cross-process state (background task UI)."""

from __future__ import annotations

import logging

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def get_sync_redis() -> redis.Redis | None:
    """Return a sync Redis client, or None if connection fails (API stays up)."""
    try:
        settings = get_settings()
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2.0)
        r.ping()
        return r
    except Exception:
        logger.warning("Redis unavailable for background task store (redis_url).", exc_info=True)
        return None


def redis_available() -> bool:
    return get_sync_redis() is not None
