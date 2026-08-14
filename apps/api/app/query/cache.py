"""P3-2 query result cache — process-local TTL + optional Redis."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60

_lock = threading.Lock()
_store: dict[str, tuple[float, dict[str, Any]]] = {}
_redis_client: Any | None = None
_redis_checked = False


def _try_redis() -> Any | None:
    """Best-effort Redis; never required for local in-process topology."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        from app.core.config import settings

        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5)
        client.ping()
        _redis_client = client
    except Exception:
        logger.debug("query cache: Redis unavailable; using process-local only", exc_info=True)
        _redis_client = None
    return _redis_client


def cache_key(
    *,
    tenant_id: str,
    metric: str,
    grains: list[str],
    filters: dict[str, Any],
    catalog_version: int,
    period_grain: str | None = None,
) -> str:
    canonical = {
        "tenant_id": tenant_id,
        "metric": (metric or "").strip().lower(),
        "grains": sorted(str(g).strip().lower() for g in grains if str(g).strip()),
        "filters": _canonicalize_filters(filters),
        "catalog_version": int(catalog_version),
        "period_grain": (str(period_grain).strip().lower() if period_grain else None),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"cip:query:v1:{digest}"


def _canonicalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if not filters:
        return {}
    out: dict[str, Any] = {}
    for k in sorted(filters.keys()):
        v = filters[k]
        if v is None or v == "":
            continue
        out[str(k)] = v
    return out


def get_cached(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            expires_at, payload = entry
            if expires_at > now:
                return dict(payload)
            _store.pop(key, None)

    client = _try_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        if isinstance(payload, dict):
            # Warm local from Redis
            with _lock:
                _store[key] = (now + DEFAULT_TTL_SECONDS, dict(payload))
            return payload
    except Exception:
        logger.debug("query cache redis get failed", exc_info=True)
    return None


def set_cached(key: str, payload: dict[str, Any], *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    expires_at = time.monotonic() + max(1, int(ttl_seconds))
    with _lock:
        _store[key] = (expires_at, dict(payload))

    client = _try_redis()
    if client is None:
        return
    try:
        client.setex(key, max(1, int(ttl_seconds)), json.dumps(payload, default=str))
    except Exception:
        logger.debug("query cache redis set failed", exc_info=True)


def clear_query_cache() -> None:
    """Test helper."""
    with _lock:
        _store.clear()
    global _redis_checked, _redis_client
    _redis_checked = False
    _redis_client = None
