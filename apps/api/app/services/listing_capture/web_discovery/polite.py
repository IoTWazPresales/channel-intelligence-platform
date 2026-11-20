"""The polite getter: every discovery request goes through it.

For each request it:

1. checks the 24 h HTTP cache (a hit sends nothing),
2. checks robots.txt for the host (a disallowed URL sends no request),
3. sends through the shared ``SiteFetchGate`` under a gate key,
4. follows redirects itself, checking robots and the gate on every hop.

``guarded_call`` applies the same robots, spacing, pause and time-budget policy once at a
third-party client's call boundary. Such a client owns its internal HTTP requests; those
requests are not individually intercepted or cached here.

A host that resolves to a private, loopback or link-local address is refused, so a search
result or a guessed name cannot point the worker at an internal service.

``raw_get`` sends ONE request without following redirects and returns ``(status, body,
location)``. Tests inject a fake with that shape.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.services.listing_capture.observation import (
    DEFAULT_RATE_LIMIT_SECONDS,
    LISTING_CAPTURE_ACCEPT_LANGUAGE,
    LISTING_CAPTURE_HTTP_TIMEOUT_SECONDS,
    LISTING_CAPTURE_USER_AGENT,
)
from app.services.listing_capture.site_fetch import STOP_PAUSED, FetchPolicy, SiteFetchGate
from app.services.listing_capture.web_discovery.cache import HttpCache, RobotsCache
from app.services.listing_capture.web_discovery.robots import (
    MODE_DISALLOW_ALL,
    RobotsRules,
    rules_from_response,
)

DEFAULT_SPACING_SECONDS = float(DEFAULT_RATE_LIMIT_SECONDS)
MAX_REDIRECT_HOPS = 5
MAX_BODY_BYTES = 2 * 1024 * 1024
DNS_TIMEOUT_SECONDS = 3.0
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ALLOWED_PORTS = frozenset({None, 80, 443})

REFUSED_ROBOTS = "robots"
REFUSED_PRIVATE = "private_address"
REFUSED_BAD_URL = "bad_url"
REFUSED_REDIRECTS = "too_many_redirects"

RawGet = Callable[[str], tuple[int, str, str | None]]
Resolve = Callable[[str], list[str]]


@dataclass(frozen=True)
class Fetched:
    status: int
    body: str
    final_url: str
    # Why nothing was sent or the answer was withheld.
    refused: str | None = None
    from_cache: bool = False


@dataclass(frozen=True)
class GuardedCall:
    status: int
    value: Any = None
    refused: str | None = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def fetch_hop(url: str) -> tuple[int, str, str | None]:
    """One GET with the shared User-Agent, no redirect following and a 2 MB body cap."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": LISTING_CAPTURE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": LISTING_CAPTURE_ACCEPT_LANGUAGE,
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=LISTING_CAPTURE_HTTP_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", None) or response.getcode())
            raw = response.read(MAX_BODY_BYTES + 1)[:MAX_BODY_BYTES]
            return status, raw.decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location") if exc.headers is not None else None
        try:
            raw = exc.read(MAX_BODY_BYTES) if exc.fp else b""
        except Exception:  # noqa: BLE001
            raw = b""
        return int(exc.code), raw.decode("utf-8", errors="replace"), location
    except (urllib.error.URLError, OSError, ValueError):
        return 0, "", None


def dns_resolve(host: str) -> list[str]:
    """The IP addresses ``host`` resolves to, within 3 seconds."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(socket.getaddrinfo, host, None)
        try:
            infos = future.result(timeout=DNS_TIMEOUT_SECONDS)
        except (FutureTimeoutError, OSError, UnicodeError):
            return []
    finally:
        executor.shutdown(wait=False)
    out: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in out:
            out.append(address)
    return out


def is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_global
    except ValueError:
        return False


class PoliteGetter:
    """Discovery HTTP and library calls under robots, spacing and the shared pause policy."""

    def __init__(
        self,
        policy: FetchPolicy,
        cache: HttpCache | None = None,
        robots: RobotsCache | None = None,
        raw_get: RawGet = fetch_hop,
        resolve: Resolve = dns_resolve,
    ) -> None:
        self.policy = policy
        self.cache = cache if cache is not None else HttpCache()
        self.robots_cache = robots if robots is not None else RobotsCache()
        self._raw_get = raw_get
        self._resolve = resolve
        self._gates: dict[str, SiteFetchGate] = {}
        self._run_rules: dict[str, RobotsRules] = {}
        self._public_hosts: dict[str, bool] = {}
        self.requests = 0

    # ------------------------------------------------------------------ gates

    def gate(self, gate_key: str, spacing: float | None = None) -> SiteFetchGate:
        key = (gate_key or "").strip().lower()
        gate = self._gates.get(key)
        if gate is None:
            gate = SiteFetchGate(
                site_key=key,
                spacing_seconds=float(DEFAULT_SPACING_SECONDS if spacing is None else spacing),
                policy=self.policy,
            )
            self._gates[key] = gate
        elif spacing is not None and float(spacing) > gate.spacing_seconds:
            gate.spacing_seconds = float(spacing)
        return gate

    def gate_summary(self, gate_key: str) -> dict[str, Any] | None:
        gate = self._gates.get((gate_key or "").strip().lower())
        return gate.summary() if gate is not None else None

    def paused(self, gate_key: str) -> bool:
        """True when this key is paused by an earlier run or this one."""
        gate = self.gate(gate_key)
        return gate.check_pause() or gate.stopped == STOP_PAUSED

    # ------------------------------------------------------------------ public API

    def guarded_call(
        self,
        url: str,
        operation: Callable[[], tuple[int, Any]],
        *,
        gate_key: str,
        spacing: float,
    ) -> GuardedCall:
        """Run one library operation under the existing gate.

        ``url`` is the actual backend endpoint used for the robots check. The operation
        returns a status and a value; exceptions propagate to the provider adapter, which
        records a search pause even when the library does not expose an HTTP status.
        SiteFetchGate records completion time in its finally block for errors as well.
        """
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower()
            port = parts.port
        except ValueError:
            return GuardedCall(0, refused=REFUSED_BAD_URL)
        if (
            parts.scheme not in ("http", "https")
            or not host
            or port not in _ALLOWED_PORTS
            or parts.username is not None
            or parts.password is not None
        ):
            return GuardedCall(0, refused=REFUSED_BAD_URL)
        gate = self.gate(gate_key, spacing)
        if not gate.can_send():
            return GuardedCall(int(gate.refused_status or 0), refused=gate.stopped)
        if not self._host_is_public(host):
            return GuardedCall(0, refused=REFUSED_PRIVATE)
        rules = self._rules_for(parts.scheme, parts.netloc, host, gate)
        if gate.stopped is not None:
            return GuardedCall(int(gate.refused_status or 0), refused=gate.stopped)
        if not rules.allowed(url):
            return GuardedCall(0, refused=REFUSED_ROBOTS)
        self.requests += 1
        status, value = gate.get(lambda _url: operation(), url)
        if gate.stopped is not None:
            return GuardedCall(int(status or 0), refused=gate.stopped)
        return GuardedCall(int(status or 0), value)

    def get(self, url: str, *, gate_key: str, spacing: float | None = None) -> Fetched:
        cached = self.cache.get_response(url)
        if cached is not None:
            status, body, final_url = cached
            return Fetched(status, body, final_url, from_cache=True)
        first_host = (urlsplit(url).hostname or "").lower()
        current = url
        hops = 0
        while True:
            parts = urlsplit(current)
            host = (parts.hostname or "").lower()
            try:
                port = parts.port
            except ValueError:
                port = -1
            if parts.scheme not in ("http", "https") or not host or port not in _ALLOWED_PORTS:
                return Fetched(0, "", current, refused=REFUSED_BAD_URL)
            key = gate_key if host == first_host else f"host:{host}"
            if not self._host_is_public(host):
                return Fetched(0, "", current, refused=REFUSED_PRIVATE)
            gate = self.gate(key, spacing)
            rules = self._rules_for(parts.scheme, parts.netloc, host, gate)
            if gate.stopped is not None:
                return Fetched(int(gate.refused_status or 0), "", current, refused=gate.stopped)
            if not rules.allowed(current):
                return Fetched(0, "", current, refused=REFUSED_ROBOTS)
            status, body, location = self._send(gate, current)
            if gate.stopped is not None:
                return Fetched(status, "", current, refused=gate.stopped)
            if status in _REDIRECT_STATUSES and location:
                hops += 1
                if hops > MAX_REDIRECT_HOPS:
                    return Fetched(status, "", current, refused=REFUSED_REDIRECTS)
                current = urljoin(current, location)
                continue
            break
        self.cache.put_response(url, status, body, current)
        return Fetched(status, body, current)

    # ------------------------------------------------------------------ internals

    def _host_is_public(self, host: str) -> bool:
        known = self._public_hosts.get(host)
        if known is None:
            addresses = self._resolve(host)
            # No address at all is not "private": the request will simply fail (status 0).
            known = all(is_public_address(address) for address in addresses)
            self._public_hosts[host] = known
        return known

    def _send(self, gate: SiteFetchGate, url: str) -> tuple[int, str, str | None]:
        self.requests += 1
        result = gate.get(self._raw_get, url)
        try:
            status = int(result[0] or 0)
        except (TypeError, ValueError, IndexError):
            status = 0
        body = result[1] if len(result) > 1 else ""
        location = result[2] if len(result) > 2 else None
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        return status, str(body or ""), (str(location) if location else None)

    def _rules_for(self, scheme: str, netloc: str, host: str, gate: SiteFetchGate) -> RobotsRules:
        known = self._run_rules.get(host)
        if known is not None:
            gate.spacing_seconds = max(gate.spacing_seconds, known.spacing_floor())
            return known
        rules = self.robots_cache.get_rules(host)
        if rules is None:
            status, body = self._fetch_robots(scheme, netloc, gate)
            if gate.stopped is not None:
                return RobotsRules(mode=MODE_DISALLOW_ALL)
            rules = rules_from_response(status, body)
            if rules.mode != MODE_DISALLOW_ALL:
                self.robots_cache.put_rules(host, rules)
        self._run_rules[host] = rules
        gate.spacing_seconds = max(gate.spacing_seconds, rules.spacing_floor())
        return rules

    def _fetch_robots(self, scheme: str, netloc: str, gate: SiteFetchGate) -> tuple[int, str]:
        url = f"{scheme}://{netloc}/robots.txt"
        for _ in range(MAX_REDIRECT_HOPS + 1):
            status, body, location = self._send(gate, url)
            if gate.stopped is not None:
                return status, ""
            if status in _REDIRECT_STATUSES and location:
                target = urljoin(url, location)
                target_host = (urlsplit(target).hostname or "").lower()
                if (
                    urlsplit(target).scheme not in ("http", "https")
                    or not self._host_is_public(target_host)
                ):
                    return 0, ""
                url = target
                continue
            return status, body
        return 0, ""
