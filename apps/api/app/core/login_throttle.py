"""Login failure throttle (N-0037): per account (normalised email) and per client address.

In-memory and per API process on purpose: login must not depend on Redis being up, and the
API runs as a single process today. Counters reset on restart and are not shared between
workers; see .eif/audit/PROGRAMME_20260924/n0037/IMPL.md for the threat note.

Sliding window: a key is blocked while it has >= limit failures inside the last `window`
seconds; Retry-After is when the oldest of those failures ages out. A blocked key is refused
before the password is checked, so even a correct password waits out the window. A successful
login clears that account's failures (not the address's, so a valid account cannot be used to
reset an address that is guessing other accounts).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import math
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from starlette.requests import Request

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Bound memory against an attacker spraying distinct emails / addresses.
_MAX_TRACKED_KEYS = 10_000

# Per-process pepper: log keys correlate within one process but cannot be reversed by
# hashing a guessed email / IPv4 space. Never log the raw email or address.
_LOG_PEPPER = secrets.token_bytes(32)


def log_key(value: str) -> str:
    return hmac.new(_LOG_PEPPER, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _is_loopback(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(ip.is_loopback or (mapped is not None and mapped.is_loopback))


def client_address(request: Request) -> str:
    """Client address for per-address throttling.

    request.client.host is the TCP peer. The Next same-origin proxy (apps/web .../route.ts)
    connects from loopback and forwards the browser's headers, so X-Forwarded-For is honoured
    only when the peer is loopback; the right-most entry is used (the hop nearest us).
    Limitation: Next 15 only fills X-Forwarded-For when the client did not send one, so a
    client can choose this value; per-account limits do not depend on it.
    """
    peer = request.client.host if request.client else ""
    if peer and _is_loopback(peer):
        xff = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return peer or "unknown"


@dataclass(frozen=True)
class ThrottleVerdict:
    reason: str  # "account" | "address"
    key: str
    retry_after: int


class LoginThrottle:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}

    def reset_all(self) -> None:
        with self._lock:
            self._failures.clear()

    def _window_and_limits(self) -> tuple[int, int, int]:
        s = get_settings()
        return (
            s.cip_login_throttle_window_seconds,
            s.cip_login_max_failures_per_account,
            s.cip_login_max_failures_per_address,
        )

    def _pruned(self, key: str, now: float, window: int) -> deque[float] | None:
        q = self._failures.get(key)
        if q is None:
            return None
        while q and q[0] <= now - window:
            q.popleft()
        if not q:
            del self._failures[key]
            return None
        return q

    def _blocked(self, key: str, limit: int, now: float, window: int) -> int | None:
        q = self._pruned(key, now, window)
        if q is None or len(q) < limit:
            return None
        # The (len - limit)th oldest failure must age out before the count drops below limit.
        return max(1, math.ceil(q[len(q) - limit] + window - now))

    def _sweep(self, now: float, window: int) -> None:
        for key in list(self._failures):
            self._pruned(key, now, window)
        overflow = len(self._failures) - _MAX_TRACKED_KEYS
        if overflow > 0:
            oldest = sorted(self._failures, key=lambda k: self._failures[k][-1])[:overflow]
            for key in oldest:
                del self._failures[key]

    def check(self, account: str, address: str) -> ThrottleVerdict | None:
        """Return a verdict when this attempt must be refused before checking the password."""
        window, acct_limit, addr_limit = self._window_and_limits()
        now = self._clock()
        with self._lock:
            ra = self._blocked(f"acct:{account}", acct_limit, now, window)
            if ra is not None:
                return ThrottleVerdict("account", account, ra)
            ra = self._blocked(f"addr:{address}", addr_limit, now, window)
            if ra is not None:
                return ThrottleVerdict("address", address, ra)
        return None

    def record_failure(self, account: str, address: str) -> list[ThrottleVerdict]:
        """Record a failed attempt; return the keys this failure has just locked."""
        window, acct_limit, addr_limit = self._window_and_limits()
        now = self._clock()
        locked: list[ThrottleVerdict] = []
        with self._lock:
            for reason, key, limit, value in (
                ("account", f"acct:{account}", acct_limit, account),
                ("address", f"addr:{address}", addr_limit, address),
            ):
                was = self._blocked(key, limit, now, window)
                self._failures.setdefault(key, deque()).append(now)
                if was is None:
                    ra = self._blocked(key, limit, now, window)
                    if ra is not None:
                        locked.append(ThrottleVerdict(reason, value, ra))
            if len(self._failures) > _MAX_TRACKED_KEYS:
                self._sweep(now, window)
        return locked

    def reset_account(self, account: str) -> None:
        with self._lock:
            self._failures.pop(f"acct:{account}", None)


login_throttle = LoginThrottle()


def log_throttle_event(event: str, verdict: ThrottleVerdict, *, account: str, address: str) -> None:
    """Structured warning: event + reason + non-reversible keys; never the password or raw email."""
    fields = {
        "event": event,
        "reason": verdict.reason,
        "account_key": log_key(account),
        "address_key": log_key(address),
        "retry_after_s": verdict.retry_after,
    }
    logger.warning(
        "login_throttle event=%s reason=%s account_key=%s address_key=%s retry_after_s=%s",
        fields["event"],
        fields["reason"],
        fields["account_key"],
        fields["address_key"],
        fields["retry_after_s"],
        extra={"login_throttle": fields},
    )
