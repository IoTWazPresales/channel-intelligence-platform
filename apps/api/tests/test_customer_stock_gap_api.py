"""N-0110: /api/v1/cst-steward/stock-gap routes (stub auth, no database)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api.v1.endpoints.cst_steward as cst_steward
import app.services.channel_intelligence.customer_stock_gap as gap_mod
import app.services.platform_audit as platform_audit
from app.core.security import Role, get_current_user
from app.main import app
from app.services import commercial_tenant_profile as profile

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    fake = MagicMock()

    @contextmanager
    def _session():
        yield fake

    monkeypatch.setattr(cst_steward, "SessionLocal", _session)
    monkeypatch.setattr(platform_audit, "record_platform_audit_committed", lambda *a, **k: None)
    yield fake
    app.dependency_overrides.clear()


def _as(role: Role):
    async def _fake_user():
        return {"id": "u1", "role": role, "tenant_id": "default", "email": None, "display_name": None}

    app.dependency_overrides[get_current_user] = _fake_user


def _row(gap: float | None, status: str = "compared", highlighted: bool = False) -> dict:
    return {"status": status, "gap_units": gap, "highlighted": highlighted}


def test_get_returns_rows_counts_and_threshold(monkeypatch) -> None:
    _as(Role.VIEWER)
    seen: dict = {}

    def fake_list(_db, **kwargs):
        seen.update(kwargs)
        return [_row(-3, highlighted=True), _row(0), _row(None, status="first_report")]

    monkeypatch.setattr(gap_mod, "list_stock_positions", fake_list)
    r = client.get("/api/v1/cst-steward/stock-gap?customer_id=5&highlighted_only=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["threshold_units"] == profile.DEFAULT_STOCK_GAP_HIGHLIGHT_UNITS
    assert body["counts"] == {
        "compared": 2,
        "highlighted": 1,
        "first_report": 1,
        "highlighted_by_cause": {
            "overwrite": 0,
            "unmatched_shipment": 0,
            "no_pod": 0,
            "no_prior_on_hand": 0,
            "repeated_report": 0,
            "unreported_weeks": 0,
            "unexplained": 0,
        },
    }
    assert seen["customer_id"] == 5 and seen["highlighted_only"] is True
    assert seen["tenant_id"] == "default"


def test_put_threshold_needs_steward_and_saves_units() -> None:
    _as(Role.VIEWER)
    assert client.put("/api/v1/cst-steward/stock-gap/settings", json={"highlight_units": 5}).status_code == 403
    _as(Role.STEWARD)
    r = client.put("/api/v1/cst-steward/stock-gap/settings", json={"highlight_units": 5})
    assert r.status_code == 200, r.text
    assert r.json() == {"threshold_units": 5.0}
    assert profile.stock_gap_highlight_units("default") == 5.0
    assert client.put("/api/v1/cst-steward/stock-gap/settings", json={"highlight_units": 0}).status_code == 422


def test_recompute_is_steward_only(monkeypatch, _isolate) -> None:
    monkeypatch.setattr(gap_mod, "recompute_all_customer_stock_positions", lambda _db, tenant_id: {"customers": 2, "positions": 9})
    _as(Role.VIEWER)
    assert client.post("/api/v1/cst-steward/stock-gap/recompute").status_code == 403
    _as(Role.ADMIN)
    r = client.post("/api/v1/cst-steward/stock-gap/recompute")
    assert r.status_code == 200, r.text
    assert r.json() == {"customers": 2, "positions": 9}
    assert _isolate.commit.called
