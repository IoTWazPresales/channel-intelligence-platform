"""N-0086: per-address login throttle is keyed on the address the proxy trusts, not on visitor headers.

The web proxy (apps/web/src/lib/proxyForwardedHeaders.ts, tested in vitest) drops every visitor-supplied
client-address header and sends exactly one X-Forwarded-For. These tests pin the API half of the contract,
through uvicorn's real proxy-header middleware as the supervisor runs it (default trusted host 127.0.0.1):

- from the loopback proxy, the key is that single X-Forwarded-For value;
- from any other peer, X-Forwarded-For is ignored, so rotating it never yields a fresh key;
- IPv6 clients are keyed per /64, so rotating inside one subscriber prefix does not either.

No database: get_db is overridden with an in-memory fake (same fake as test_auth_login_throttle.py).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.deps import get_db
from app.core import login_throttle as lt
from app.core.config import get_settings
from app.main import app

LOGIN = "/api/v1/auth/login"
BAD = "bad-" + "pw"


class _Result:
    def scalar_one_or_none(self):
        return None


class _NoUsers:
    async def execute(self, stmt):
        return _Result()

    def add(self, obj):
        return None

    async def commit(self):
        return None


class _Clock:
    def __init__(self) -> None:
        self.t = 5_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(lt.login_throttle, "_clock", c)
    return c


@pytest.fixture()
def wrapped_app():
    async def _db():
        yield _NoUsers()

    app.dependency_overrides[get_db] = _db
    get_settings.cache_clear()
    try:
        # What uvicorn builds with its defaults (proxy_headers=True, forwarded_allow_ips="127.0.0.1").
        yield ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
    finally:
        app.dependency_overrides.pop(get_db, None)
        get_settings.cache_clear()


def _fail(client: TestClient, n: int, xff: str | None, start: int = 0) -> list[int]:
    codes = []
    for i in range(start, start + n):
        headers = {"x-forwarded-for": xff} if xff is not None else {}
        r = client.post(LOGIN, json={"email": f"nobody{i}@example.com", "password": BAD}, headers=headers)
        codes.append(r.status_code)
    return codes


def test_address_limit_holds_for_the_proxy_supplied_address(wrapped_app, clock) -> None:
    limit = get_settings().cip_login_max_failures_per_address
    proxy = TestClient(wrapped_app, client=("127.0.0.1", 40001))
    # The proxy always sends the visitor's CF-Connecting-IP as the single X-Forwarded-For.
    assert set(_fail(proxy, limit, "198.51.100.20")) == {401}
    # A new account from the same address is refused before the password check.
    assert _fail(proxy, 1, "198.51.100.20", start=limit) == [429]
    # A different visitor behind the same proxy is not affected.
    assert _fail(proxy, 1, "203.0.113.77", start=limit + 1) == [401]


def test_spoofed_xff_from_a_non_loopback_peer_does_not_change_the_key(wrapped_app, clock) -> None:
    limit = get_settings().cip_login_max_failures_per_address
    direct = TestClient(wrapped_app, client=("192.0.2.50", 40002))
    codes = []
    for i in range(limit + 1):
        # A fresh, made-up X-Forwarded-For on every attempt.
        codes += _fail(direct, 1, f"10.0.{i}.{i}", start=i)
    assert codes[:limit] == [401] * limit
    assert codes[limit] == 429


def test_ipv6_rotation_inside_one_64_is_one_key(wrapped_app, clock) -> None:
    limit = get_settings().cip_login_max_failures_per_address
    proxy = TestClient(wrapped_app, client=("127.0.0.1", 40003))
    codes = []
    for i in range(limit + 1):
        codes += _fail(proxy, 1, f"2001:db8:aa:bb::{i + 1:x}", start=i)
    assert codes[:limit] == [401] * limit
    assert codes[limit] == 429
    # Another /64 is a different key.
    assert _fail(proxy, 1, "2001:db8:aa:cc::1", start=limit + 1) == [401]


@pytest.mark.parametrize(
    ("value", "key"),
    [
        ("203.0.113.9", "203.0.113.9"),
        ("2001:db8:aa:bb::1", "2001:db8:aa:bb::/64"),
        ("2001:db8:aa:bb:ffff:ffff:ffff:ffff", "2001:db8:aa:bb::/64"),
        ("::ffff:198.51.100.7", "198.51.100.7"),
        ("testclient", "testclient"),
        ("", "unknown"),
    ],
)
def test_throttle_address_key(value: str, key: str) -> None:
    assert lt.throttle_address_key(value) == key


def _request(peer: str, xff: str | None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "method": "POST", "path": LOGIN, "headers": headers, "client": (peer, 1)})


def test_client_address_keys_ipv6_proxy_value_per_64() -> None:
    assert lt.client_address(_request("127.0.0.1", "2001:db8:1:2::99")) == "2001:db8:1:2::/64"
    assert lt.client_address(_request("127.0.0.1", "127.0.0.1")) == "127.0.0.1"
