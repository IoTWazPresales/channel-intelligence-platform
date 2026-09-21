"""Router-level auth gate (2026-09-21).

Before the gate, auth was per-endpoint: with CIP_AUTH_MODE=session, 127 of 229 GET routes
still served data to anonymous callers. The gate puts get_current_user on api_router itself,
leaving only /auth/login public. These tests flip the process into session mode for their
duration and restore it after; conftest pins stub for everything else.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture()
def session_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CIP_AUTH_MODE", "session")
    get_settings.cache_clear()
    assert get_settings().cip_auth_mode == "session"
    try:
        yield
    finally:
        get_settings.cache_clear()


# Routes that had NO endpoint-level auth before the gate (sampled from the 2026-09-21 enumeration).
PREVIOUSLY_OPEN = [
    "/api/v1/customers?page=1&page_size=1",
    "/api/v1/products?page=1&page_size=1",
    "/api/v1/market/placeholders",
    "/api/v1/cpor/meta/lifecycle",
    "/api/v1/imports/jobs",
    "/api/v1/brief/signals",
    "/api/v1/dev/database-wipe",
    "/api/v1/auth/me",
]


def test_session_mode_denies_every_route_without_a_bearer(session_mode) -> None:
    with TestClient(app) as client:
        for path in PREVIOUSLY_OPEN:
            r = client.get(path)
            assert r.status_code == 401, f"{path} -> {r.status_code} (expected 401 without a token)"


def test_session_mode_rejects_forged_identity_headers(session_mode) -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/customers?page=1&page_size=1", headers={"X-User-Role": "admin", "X-User-Id": "1"})
        assert r.status_code == 401


def test_login_stays_reachable_and_health_stays_public(session_mode) -> None:
    with TestClient(app) as client:
        # Wrong credentials: 401 from the login handler itself, never 404 (route must exist ungated).
        r = client.post("/api/v1/auth/login", json={"email": "admin@local", "password": "definitely-not-the-password"})
        assert r.status_code == 401
        assert client.get("/health").status_code == 200


def test_stub_mode_is_unchanged_by_the_gate() -> None:
    # conftest pins CIP_AUTH_MODE=stub; the router dependency resolves admin@local and never raises.
    get_settings.cache_clear()
    assert get_settings().cip_auth_mode == "stub"
    with TestClient(app) as client:
        assert client.get("/api/v1/market/placeholders").status_code == 200
        assert client.get("/api/v1/cpor/meta/lifecycle").status_code == 200
