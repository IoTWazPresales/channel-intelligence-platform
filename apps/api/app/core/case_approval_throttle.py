"""Public case-approval rate limit (N-0100).

In-memory and per API process, same shape as the login throttle: a sliding window
of request times, not shared across workers, and not stored. Login must not be
involved. This limiter does not authenticate and does not read a role.

Every GET and POST on /api/v1/case-approval counts, including a miss, so one token
cannot be hammered and one client cannot spray tokens. A request already over a
limit is refused before the link is looked up. The raw token is never stored or
logged; the bucket key is an HMAC.

A normal customer open plus one decision fits inside both limits. Excess calls
are refused until the oldest counted call ages out of the window.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.core.login_throttle import client_address

logger = logging.getLogger(__name__)

# One open, refreshes, and one decision fit. A script on one link does not.
MAX_PER_TOKEN = 20
# Bounds a flood and token spraying from one client address. Shared with the
# login throttle's address rule (loopback proxy, IPv6 /64) via client_address.
MAX_PER_CLIENT = 100
WINDOW_SECONDS = 900

_MAX_TRACKED_KEYS = 10_000
_PEPPER = secrets.token_bytes(32)

# Re-export so the public route does not import the login module itself.
__all__ = [
    "CaseApprovalThrottle",
    "ThrottleVerdict",
    "case_approval_throttle",
    "client_address",
    "log_throttle_event",
]


def log_key(value: str) -> str:
    return hmac.new(_PEPPER, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _token_bucket(token: str | None) -> str | None:
    normalized = (token or "").strip()
    if not normalized:
        return None
    digest = hmac.new(_PEPPER, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return "token:" + digest


@dataclass(frozen=True)
class ThrottleVerdict:
    reason: str  # "token" | "client"
    retry_after: int


class CaseApprovalThrottle:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self.window_seconds = WINDOW_SECONDS
        self.max_per_token = MAX_PER_TOKEN
        self.max_per_client = MAX_PER_CLIENT

    def reset_all(self) -> None:
        with self._lock:
            self._hits.clear()

    def _pruned(self, key: str, now: float, window: int) -> deque[float] | None:
        q = self._hits.get(key)
        if q is None:
            return None
        while q and q[0] <= now - window:
            q.popleft()
        if not q:
            del self._hits[key]
            return None
        return q

    def _blocked(self, key: str, limit: int, now: float, window: int) -> int | None:
        q = self._pruned(key, now, window)
        if q is None or len(q) < limit:
            return None
        return max(1, math.ceil(q[len(q) - limit] + window - now))

    def _append(self, key: str, now: float) -> None:
        self._hits.setdefault(key, deque()).append(now)

    def _sweep(self, now: float, window: int) -> None:
        for key in list(self._hits):
            self._pruned(key, now, window)
        overflow = len(self._hits) - _MAX_TRACKED_KEYS
        if overflow > 0:
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:overflow]
            for key in oldest:
                del self._hits[key]

    def admit(self, token: str | None, address: str) -> ThrottleVerdict | None:
        """Count this call. Return a verdict when it is already over a limit.

        The call that reaches the limit is allowed. The next call is not, and it
        is not recorded, so the window does not grow while the client is refused.
        """
        window = self.window_seconds
        token_limit = self.max_per_token
        client_limit = self.max_per_client
        now = self._clock()
        token_key = _token_bucket(token)
        client_key = "client:" + (address or "unknown")
        with self._lock:
            client_retry = self._blocked(client_key, client_limit, now, window)
            token_retry = None
            if token_key is not None:
                token_retry = self._blocked(token_key, token_limit, now, window)
            token_first = token_retry is not None and (
                client_retry is None or token_retry >= client_retry
            )
            if client_retry is not None or token_retry is not None:
                if token_first:
                    return ThrottleVerdict("token", token_retry)
                return ThrottleVerdict("client", int(client_retry or 1))
            self._append(client_key, now)
            if token_key is not None:
                self._append(token_key, now)
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._sweep(now, window)
        return None


case_approval_throttle = CaseApprovalThrottle()


def log_throttle_event(verdict: ThrottleVerdict, *, token: str, address: str) -> None:
    """Structured warning. token_key and address_key are not reversible to the raw values."""
    fields = {
        "event": "throttled",
        "reason": verdict.reason,
        "token_key": log_key((token or "").strip()),
        "address_key": log_key(address or "unknown"),
        "retry_after_s": verdict.retry_after,
    }
    logger.warning(
        "case_approval_throttle event=%s reason=%s token_key=%s address_key=%s retry_after_s=%s",
        fields["event"],
        fields["reason"],
        fields["token_key"],
        fields["address_key"],
        fields["retry_after_s"],
        extra={"case_approval_throttle": fields},
    )
