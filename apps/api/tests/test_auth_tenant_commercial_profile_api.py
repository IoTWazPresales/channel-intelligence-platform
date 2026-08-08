"""BACKLOG-096 (P6) — GET/PUT /api/v1/auth/tenant-commercial-profile (stub auth, no DB writes)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import Role, get_current_user
from app.main import app
from app.services import commercial_tenant_profile as profile

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_tenant_profiles_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    yield


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _stub_user(role: Role = Role.ADMIN):
    async def _fake_user():
        return {"id": "test-user", "role": role, "tenant_id": "default", "email": None, "display_name": None}

    return _fake_user


def test_get_returns_defaults_when_no_override_saved() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.get("/api/v1/auth/tenant-commercial-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["constraint_axis"] == profile.CONSTRAINT_AXIS
    assert body["overrides_present"] == []
    assert body["tenant_id"] == "default"


def test_put_persists_override_and_get_reflects_it() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.put(
        "/api/v1/auth/tenant-commercial-profile",
        json={"constraint_axis": "support_pct", "over_budget_action": "warn"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["constraint_axis"] == "support_pct"
    assert body["over_budget_action"] == "warn"
    assert sorted(body["overrides_present"]) == ["constraint_axis", "over_budget_action"]

    r2 = client.get("/api/v1/auth/tenant-commercial-profile")
    assert r2.json()["constraint_axis"] == "support_pct"


def test_put_rejects_invalid_value() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.put(
        "/api/v1/auth/tenant-commercial-profile",
        json={"pm_attribution_mode": "not_a_real_mode"},
    )
    assert r.status_code == 400
    assert "pm_attribution_mode" in r.json()["detail"]


def test_put_requires_admin_role() -> None:
    app.dependency_overrides[get_current_user] = _stub_user(Role.VIEWER)
    r = client.put(
        "/api/v1/auth/tenant-commercial-profile",
        json={"constraint_axis": "dual"},
    )
    assert r.status_code == 403
