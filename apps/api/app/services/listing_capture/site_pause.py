"""Per-site pause after a 403/429 refusal (N-0085 U1, D-0063).

A refusal pauses that marketplace for 1 h; a further refusal right after a pause
doubles it, up to 24 h. A good response from the site clears the record.

There is no site-state table yet (U2 adds ``listing_site_state``), so the record lives
in Redis under ``cip:listing_capture:site_pause:<marketplace>`` with a TTL of the pause
plus 24 h (the TTL is the memory that lets the next pause double), on the app's
``redis_url`` (``get_settings()``), so the worker and the API's manual poll share it.
Only when Redis is not reachable (connection refused, timeout) is the record kept in
this process, with a warning logged once per outage; any other error is raised. Not
durable across a Redis flush or a worker restart without Redis — U2's migration makes
it durable.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import redis

from app.core.config import get_settings
from app.services.listing_capture.observation import SITE_PAUSE_BASE_HOURS, SITE_PAUSE_MAX_HOURS

logger = logging.getLogger(__name__)

KEY_PREFIX = "cip:listing_capture:site_pause:"
MEMORY_HOURS = 24  # how long after a pause ends the next refusal still doubles it


class SitePauseStore(Protocol):
    def get(self, marketplace: str) -> dict[str, Any] | None: ...

    def set(self, marketplace: str, record: dict[str, Any], *, ttl_seconds: int) -> None: ...

    def delete(self, marketplace: str) -> None: ...


class MemorySitePauseStore:
    """Process-local store (tests, and the fallback when Redis is unavailable)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def get(self, marketplace: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._data.get(marketplace)
            if entry is None:
                return None
            expires, record = entry
            if datetime.now(timezone.utc) >= expires:
                self._data.pop(marketplace, None)
                return None
            return dict(record)

    def set(self, marketplace: str, record: dict[str, Any], *, ttl_seconds: int) -> None:
        with self._lock:
            self._data[marketplace] = (
                datetime.now(timezone.utc) + timedelta(seconds=int(ttl_seconds)),
                dict(record),
            )

    def delete(self, marketplace: str) -> None:
        with self._lock:
            self._data.pop(marketplace, None)


class RedisSitePauseStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, marketplace: str) -> dict[str, Any] | None:
        raw = self._client.get(KEY_PREFIX + marketplace)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def set(self, marketplace: str, record: dict[str, Any], *, ttl_seconds: int) -> None:
        self._client.set(KEY_PREFIX + marketplace, json.dumps(record), ex=int(ttl_seconds))

    def delete(self, marketplace: str) -> None:
        self._client.delete(KEY_PREFIX + marketplace)


_memory_store = MemorySitePauseStore()

# Only these mean "Redis is not reachable right now" (refused/reset connection, timeout,
# DNS/socket failure). Anything else (a code or configuration error) is raised, not
# hidden behind the process-local fallback (N-0101 round 2, GOV-008 defect D1).
_REDIS_UNREACHABLE_ERRORS: tuple[type[BaseException], ...] = (
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
    OSError,
)
_fallback_warned = False


def _redis_client() -> redis.Redis:
    """Client on the app's ``redis_url`` (the same settings source the worker uses)."""
    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=2)


def default_site_pause_store() -> SitePauseStore:
    """Redis when reachable, else the process-local store (warned once per outage)."""
    global _fallback_warned
    client = _redis_client()
    try:
        client.ping()
    except _REDIS_UNREACHABLE_ERRORS as exc:
        if not _fallback_warned:
            _fallback_warned = True
            logger.warning(
                "listing capture: Redis unreachable (%s: %s); site pauses kept in this process only",
                type(exc).__name__,
                exc,
            )
        return _memory_store
    if _fallback_warned:
        logger.warning("listing capture: Redis reachable again; site pauses stored in Redis")
        _fallback_warned = False
    return RedisSitePauseStore(client)


def _parse_until(record: dict[str, Any] | None) -> datetime | None:
    if not record or not record.get("until"):
        return None
    try:
        until = datetime.fromisoformat(str(record["until"]))
    except ValueError:
        return None
    return until if until.tzinfo else until.replace(tzinfo=timezone.utc)


def paused_until(store: SitePauseStore, marketplace: str, *, now: datetime) -> datetime | None:
    """When the site's pause ends, or None when it is not paused now."""
    try:
        until = _parse_until(store.get(marketplace))
    except Exception:  # noqa: BLE001
        logger.warning("listing capture: site pause read failed for %s", marketplace, exc_info=True)
        return None
    return until if until is not None and now < until else None


def has_pause_record(store: SitePauseStore, marketplace: str) -> bool:
    """A remembered (possibly expired) pause exists — a good response should clear it."""
    try:
        return bool(store.get(marketplace))
    except Exception:  # noqa: BLE001
        return False


def pause_site(
    store: SitePauseStore,
    marketplace: str,
    *,
    http_status: int,
    now: datetime,
) -> dict[str, Any]:
    """Record a refusal: 1 h, or double the previous pause (max 24 h) if it is remembered."""
    try:
        prev = store.get(marketplace)
    except Exception:  # noqa: BLE001
        prev = None
    prev_hours = int((prev or {}).get("hours") or 0)
    hours = min(prev_hours * 2, SITE_PAUSE_MAX_HOURS) if prev_hours else SITE_PAUSE_BASE_HOURS
    until = now + timedelta(hours=hours)
    record = {
        "marketplace": marketplace,
        "http_status": int(http_status),
        "paused_at": now.isoformat(),
        "until": until.isoformat(),
        "hours": hours,
    }
    try:
        store.set(marketplace, record, ttl_seconds=(hours + MEMORY_HOURS) * 3600)
    except Exception:  # noqa: BLE001
        logger.warning("listing capture: site pause write failed for %s", marketplace, exc_info=True)
    logger.warning(
        "listing capture: %s refused with HTTP %s; paused %s h until %s",
        marketplace,
        http_status,
        hours,
        record["until"],
    )
    return record


def clear_site_pause(store: SitePauseStore, marketplace: str) -> None:
    try:
        store.delete(marketplace)
    except Exception:  # noqa: BLE001
        logger.warning("listing capture: site pause clear failed for %s", marketplace, exc_info=True)
