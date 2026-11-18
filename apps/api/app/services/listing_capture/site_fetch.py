"""Shared per-site fetch policy: request spacing and the 403/429 site pause.

The listing poll (``registry.poll_listings_sync``) and catalogue discovery
(``discovery``) both send requests to customer sites. Both use the same rules:

- Spacing per site: ``listing_site.rate_limit_seconds`` (``DEFAULT_RATE_LIMIT_SECONDS``
  when empty) between the end of one request to a site and the start of the next.
- A site paused by an earlier 403/429 (``site_pause``) gets no request until the pause ends.
- A 403/429 pauses the site (1 h, doubling up to 24 h) and nothing more is sent to it in
  this run. A refusal body is never returned, so it cannot be parsed as a product page.
- A 200 from a site that has a remembered pause clears the record.
- A run stops starting new requests once its time budget is spent, rather than sleeping
  past it.

Pause records are keyed by the site key (the listing's ``marketplace``), so a pause set by
discovery holds the poll back and the other way round.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.listing_capture import site_pause
from app.services.listing_capture.observation import (
    DEFAULT_RATE_LIMIT_SECONDS,
    POLL_RUN_TIME_LIMIT_SECONDS,
    SITE_PAUSE_HTTP_STATUSES,
)

STOP_PAUSED = "site_paused"
STOP_TIME_LIMIT = "time_limit"

# The steward's "autoconfigure" button waits for its answer, so each of its two phases
# (discovery, then the reader probe) gets this budget instead of the 10-minute run budget.
STEWARD_RUN_TIME_LIMIT_SECONDS = 45.0

_HttpGet = Callable[..., tuple[int, Any]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def site_spacing_seconds(rate_limit_seconds: Any) -> float:
    """The configured spacing for a site, or the shared default when it is empty."""
    if rate_limit_seconds is None:
        return float(DEFAULT_RATE_LIMIT_SECONDS)
    try:
        value = float(rate_limit_seconds)
    except (TypeError, ValueError):
        return float(DEFAULT_RATE_LIMIT_SECONDS)
    return max(value, 0.0)


@dataclass
class FetchPolicy:
    """Clock, sleep, pause store and time budget for one run (injectable for tests)."""

    store: Any = None
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = _utcnow
    time_limit_seconds: float = POLL_RUN_TIME_LIMIT_SECONDS
    started: float | None = None
    # When each site (lower-cased key) last finished a request in this run. Shared by every
    # gate on this policy, so two customers on one site are still spaced.
    last_request_at: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = site_pause.default_site_pause_store()
        if self.started is None:
            self.started = self.clock()

    def elapsed(self) -> float:
        return self.clock() - float(self.started or 0.0)

    def time_left(self) -> float:
        return float(self.time_limit_seconds) - self.elapsed()

    def fork(self) -> FetchPolicy:
        """A new budget for the next phase, sharing the pause store and per-site spacing."""
        return FetchPolicy(
            store=self.store,
            clock=self.clock,
            sleep=self.sleep,
            now=self.now,
            time_limit_seconds=self.time_limit_seconds,
            last_request_at=self.last_request_at,
        )


def default_fetch_policy() -> FetchPolicy:
    return FetchPolicy()


@dataclass
class SiteFetchGate:
    """Sends requests to one site under the shared policy. ``get`` matches ``http_get``."""

    site_key: str
    spacing_seconds: float
    policy: FetchPolicy
    stopped: str | None = None
    refused_status: int | None = None
    paused_until: datetime | None = None
    pause_record: dict[str, Any] | None = None
    requests: int = 0
    _checked: bool = False
    _had_record: bool = False

    @property
    def key(self) -> str:
        return (self.site_key or "").strip().lower()

    def check_pause(self) -> bool:
        """True when the site is paused now (checked once per gate)."""
        if not self._checked:
            self._checked = True
            until = site_pause.paused_until(self.policy.store, self.key, now=self.policy.now())
            if until is not None:
                self.paused_until = until
                self.stopped = STOP_PAUSED
            else:
                self._had_record = site_pause.has_pause_record(self.policy.store, self.key)
        return self.paused_until is not None

    def can_send(self) -> bool:
        if self.stopped is not None:
            return False
        if self.check_pause():
            return False
        if self.policy.time_left() <= 0:
            self.stopped = STOP_TIME_LIMIT
            return False
        return True

    def get(
        self, http_get: _HttpGet, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, Any]:
        if not self.can_send():
            return int(self.refused_status or 0), ""
        last_at = self.policy.last_request_at.get(self.key)
        if last_at is not None and self.spacing_seconds > 0:
            wait = self.spacing_seconds - (self.policy.clock() - last_at)
            if wait > 0:
                if wait >= self.policy.time_left():
                    self.stopped = STOP_TIME_LIMIT
                    return 0, ""
                self.policy.sleep(wait)
        self.requests += 1
        try:
            result = http_get(url, headers=headers) if headers else http_get(url)
        finally:
            self.policy.last_request_at[self.key] = self.policy.clock()
        status = result[0] if isinstance(result, tuple) and result else 0
        try:
            code = int(status or 0)
        except (TypeError, ValueError):
            code = 0
        if code in SITE_PAUSE_HTTP_STATUSES:
            self.refused_status = code
            self.stopped = STOP_PAUSED
            self.pause_record = site_pause.pause_site(
                self.policy.store, self.key, http_status=code, now=self.policy.now()
            )
            return code, ""
        if code == 200 and self._had_record:
            site_pause.clear_site_pause(self.policy.store, self.key)
            self._had_record = False
        return result

    def bind(self, http_get: _HttpGet) -> Callable[..., tuple[int, Any]]:
        def guarded(url: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
            return self.get(http_get, url, headers=headers)

        return guarded

    def summary(self) -> dict[str, Any] | None:
        if self.stopped is None:
            return None
        out: dict[str, Any] = {"stopped": self.stopped, "requests": self.requests}
        if self.paused_until is not None:
            out["paused_until"] = self.paused_until.isoformat()
        if self.pause_record is not None:
            out["pause"] = dict(self.pause_record)
        return out
