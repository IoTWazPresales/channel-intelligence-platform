"""N-0037: login rate limit / lockout, non-enumeration, client address derivation.

No database: get_db is overridden with an in-memory fake, so nothing touches cip.
The throttle clock is replaced with a controllable one; conftest resets throttle state per test.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.deps import get_db
from app.api.v1.endpoints import auth as auth_ep
from app.core import login_throttle as lt
from app.core.config import get_settings
from app.core.password import DUMMY_PASSWORD_HASH, hash_password
from app.main import app

LOGIN = "/api/v1/auth/login"
EMAIL = "user@example.com"
GOOD = "good-" + "pw"
BAD = "bad-" + "pw"
_HASH = hash_password(GOOD)


class _Result:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, users: dict[str, SimpleNamespace]):
        self.users = users
        self.added: list = []

    async def execute(self, stmt):
        email = next(iter(stmt.compile().params.values()))
        return _Result(self.users.get(email))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


class _Clock:
    def __init__(self) -> None:
        self.t = 1_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(lt.login_throttle, "_clock", c)
    return c


@pytest.fixture()
def client():
    user = SimpleNamespace(
        id=1,
        email=EMAIL,
        password_hash=_HASH,
        is_active=True,
        role="admin",
        tenant_id="default",
        display_name="User",
    )
    fake = _FakeSession({EMAIL: user})

    async def _db():
        yield fake

    app.dependency_overrides[get_db] = _db
    get_settings.cache_clear()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        get_settings.cache_clear()


def _login(client: TestClient, email: str = EMAIL, password: str = BAD):
    return client.post(LOGIN, json={"email": email, "password": password})


def test_defaults_are_settings_not_literals() -> None:
    s = get_settings()
    assert s.cip_login_throttle_enabled is True
    assert s.cip_login_max_failures_per_account == 5
    assert s.cip_login_max_failures_per_address == 20
    assert s.cip_login_throttle_window_seconds == 900


def test_account_throttled_after_limit_with_retry_after(client, clock) -> None:
    for _ in range(5):
        assert _login(client).status_code == 401
    r = _login(client)
    assert r.status_code == 429
    assert r.json() == {"detail": "Too many login attempts. Try again later."}
    assert r.headers["Retry-After"] == "900"
    clock.t += 600
    assert _login(client).headers["Retry-After"] == "300"


def test_lockout_refuses_correct_password_until_window_passes(client, clock) -> None:
    for _ in range(5):
        _login(client)
    # Email normalisation: case / whitespace variants hit the same account key.
    r = _login(client, email="  USER@Example.com ", password=GOOD)
    assert r.status_code == 429
    clock.t += 900
    ok = _login(client, password=GOOD)
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["email"] == EMAIL


def test_successful_login_resets_account_counter(client, clock) -> None:
    for _ in range(4):
        assert _login(client).status_code == 401
    assert _login(client, password=GOOD).status_code == 200
    # Counter reset: another 4 failures are 401, not 429.
    for _ in range(4):
        assert _login(client).status_code == 401
    assert _login(client, password=GOOD).status_code == 200


def test_per_address_throttle_across_accounts(client, clock, monkeypatch) -> None:
    monkeypatch.setenv("CIP_LOGIN_MAX_FAILURES_PER_ADDRESS", "3")
    get_settings.cache_clear()
    for i in range(3):
        assert _login(client, email=f"spray{i}@example.com").status_code == 401
    r = _login(client, email="fresh@example.com")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # The address throttle also refuses a correct password for a different, unlocked account.
    assert _login(client, password=GOOD).status_code == 429


def test_unknown_user_and_wrong_password_are_indistinguishable(client, clock, monkeypatch) -> None:
    seen: list[str] = []
    orig = auth_ep.verify_password

    def spy(password: str, password_hash: str) -> bool:
        seen.append(password_hash)
        return orig(password, password_hash)

    monkeypatch.setattr(auth_ep, "verify_password", spy)
    wrong = _login(client)
    unknown = _login(client, email="nobody@example.com")
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json()) == (
        401,
        {"detail": "Invalid credentials"},
    )
    # Timing: the unknown user still pays a PBKDF2 verify, against the dummy hash.
    assert seen == [_HASH, DUMMY_PASSWORD_HASH]

    # A locked unknown email looks exactly like a locked real account.
    for _ in range(4):
        _login(client)
        _login(client, email="nobody@example.com")
    a, b = _login(client), _login(client, email="nobody@example.com")
    assert a.status_code == 429
    assert (a.status_code, a.json(), a.headers["Retry-After"]) == (
        b.status_code,
        b.json(),
        b.headers["Retry-After"],
    )


def test_lockout_and_throttle_logged_without_raw_email(client, clock, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.core.login_throttle")
    for _ in range(5):
        _login(client)
    _login(client)
    records = [r for r in caplog.records if r.name == "app.core.login_throttle"]
    assert [r.login_throttle["event"] for r in records] == ["lockout", "throttled"]
    for r in records:
        fields = r.login_throttle
        assert fields["reason"] == "account"
        assert fields["account_key"] == lt.log_key(EMAIL)
        text = r.getMessage()
        assert EMAIL not in text and BAD not in text


def test_throttle_can_be_disabled(client, clock, monkeypatch) -> None:
    monkeypatch.setenv("CIP_LOGIN_THROTTLE_ENABLED", "false")
    get_settings.cache_clear()
    for _ in range(8):
        assert _login(client).status_code == 401


def test_stub_mode_gated_routes_unaffected_by_lockout(client, clock) -> None:
    assert get_settings().cip_auth_mode == "stub"
    for _ in range(6):
        _login(client)
    assert client.get("/api/v1/market/placeholders").status_code == 200


def _request(peer: str | None, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    scope = {
        "type": "http",
        "method": "POST",
        "path": LOGIN,
        "headers": headers,
        "client": (peer, 5555) if peer else None,
    }
    return Request(scope)


@pytest.mark.parametrize(
    ("peer", "xff", "expected"),
    [
        ("127.0.0.1", "203.0.113.9", "203.0.113.9"),  # Next proxy on loopback: trust XFF
        ("::1", "198.51.100.1, 203.0.113.9", "203.0.113.9"),  # right-most hop
        ("::ffff:127.0.0.1", "203.0.113.9", "203.0.113.9"),
        ("127.0.0.1", None, "127.0.0.1"),
        ("192.0.2.50", "203.0.113.9", "192.0.2.50"),  # non-loopback peer: XFF ignored
        ("testclient", "203.0.113.9", "testclient"),
        (None, None, "unknown"),
    ],
)
def test_client_address_trusts_xff_only_from_loopback(peer, xff, expected) -> None:
    assert lt.client_address(_request(peer, xff)) == expected
