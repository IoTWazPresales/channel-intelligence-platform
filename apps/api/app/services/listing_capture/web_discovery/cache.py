"""Operational caches for web discovery, kept in the run-state store (Redis, process-local fallback).

These hold fetched pages, robots.txt records and search outcomes. They are operational data, never
product data, so Preview may write them. Keys:

- ``wd:http:<sha256(url)>``: a 200 response, gzip-compressed, 24 h, only when under 1 MB
- ``wd:robots:<host>``: parsed robots rules, 24 h (a failed fetch is never persisted)
- ``wd:search:<provider>:<sha256(query)>``: a successful search outcome, 7 days
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from app.services.listing_capture import site_pause
from app.services.listing_capture.observation import compress_snapshot, decompress_snapshot
from app.services.listing_capture.web_discovery.robots import RobotsRules

HTTP_TTL_SECONDS = 24 * 3600
ROBOTS_TTL_SECONDS = 24 * 3600
SEARCH_TTL_SECONDS = 7 * 24 * 3600
MAX_CACHED_BODY_BYTES = 1_000_000


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class JsonCache:
    """A small JSON key-value cache over a ``SitePauseStore``-shaped store."""

    def __init__(self, store: Any | None = None) -> None:
        self._store = store

    @property
    def store(self) -> Any:
        if self._store is None:
            self._store = site_pause.default_run_state_store()
        return self._store

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            value = self.store.get(key)
        except Exception:  # noqa: BLE001 - a cache read never fails a run
            return None
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        try:
            self.store.set(key, value, ttl_seconds=int(ttl_seconds))
        except Exception:  # noqa: BLE001 - a cache write never fails a run
            return None


class HttpCache(JsonCache):
    def _key(self, url: str) -> str:
        return f"wd:http:{sha256_hex(url)}"

    def get_response(self, url: str) -> tuple[int, str, str] | None:
        """``(status, body, final_url)`` for a cached 200, or None."""
        record = self.get(self._key(url))
        if not record or int(record.get("status") or 0) != 200:
            return None
        try:
            body = decompress_snapshot(base64.b64decode(str(record.get("gz") or "")))
        except Exception:  # noqa: BLE001
            return None
        return 200, body, str(record.get("final_url") or url)

    def put_response(self, url: str, status: int, body: str, final_url: str) -> bool:
        raw = body.encode("utf-8")
        if int(status) != 200 or len(raw) >= MAX_CACHED_BODY_BYTES:
            return False
        blob = base64.b64encode(compress_snapshot(raw)).decode("ascii")
        self.set(
            self._key(url),
            {"status": 200, "final_url": final_url, "gz": blob},
            ttl_seconds=HTTP_TTL_SECONDS,
        )
        return True


class RobotsCache(JsonCache):
    def _key(self, host: str) -> str:
        return f"wd:robots:{host.lower()}"

    def get_rules(self, host: str) -> RobotsRules | None:
        record = self.get(self._key(host))
        return RobotsRules.from_dict(record) if record else None

    def put_rules(self, host: str, rules: RobotsRules) -> None:
        self.set(self._key(host), rules.to_dict(), ttl_seconds=ROBOTS_TTL_SECONDS)


class SearchCache(JsonCache):
    def key(self, provider: str, query: str) -> str:
        return f"wd:search:{provider}:{sha256_hex(query)}"

    def get_outcome(self, provider: str, query: str) -> dict[str, Any] | None:
        return self.get(self.key(provider, query))

    def put_outcome(self, provider: str, query: str, outcome: dict[str, Any]) -> None:
        self.set(self.key(provider, query), outcome, ttl_seconds=SEARCH_TTL_SECONDS)
