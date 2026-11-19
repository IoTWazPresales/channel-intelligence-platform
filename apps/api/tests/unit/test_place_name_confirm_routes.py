"""Confirm routes for proposed store pins (lane L5). The service is stubbed: no database.

The role check is the real ``require_roles(Role.STEWARD)``; only the user and the session are faked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.api.v1.endpoints import store_dc as endpoint
from app.core.security import Role, get_current_user
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch, role: Role, result: dict | None = None):
    calls: list[dict] = []

    def fake_confirm(db, *, tenant_id, items, actor):
        calls.append({"tenant_id": tenant_id, "items": items, "actor": actor})
        return result or {"saved": [{"site_label": items[0]["site_label"], "pinned": True}], "failed": []}

    monkeypatch.setattr(endpoint, "confirm_pins", fake_confirm)
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/store-dc")
    app.dependency_overrides[endpoint._sync_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user] = lambda: {"tenant_id": "unit-tenant", "role": role, "id": "unit-user"}
    return TestClient(app), calls


@pytest.mark.parametrize("path", ["/store-dc/pins/confirm", "/store-dc/pins/confirm-bulk"])
@pytest.mark.parametrize("role", [Role.VIEWER, Role.PLANNER])
def test_only_a_steward_or_admin_can_confirm(monkeypatch, path, role):
    client, calls = _client(monkeypatch, role)
    body = {"customer_id": 1, "site_label": "S1"}
    response = client.post(path, json=body if path.endswith("confirm") else {"pins": [body]})
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize("role", [Role.STEWARD, Role.ADMIN])
def test_a_steward_confirms_one_proposal_with_no_coordinates(monkeypatch, role):
    client, calls = _client(monkeypatch, role)
    response = client.post("/store-dc/pins/confirm", json={"customer_id": 4, "site_label": "S1"})
    assert response.status_code == 200
    assert response.json()["pinned"] is True
    assert calls[0]["items"] == [{"customer_id": 4, "site_label": "S1", "latitude": None, "longitude": None}]
    assert calls[0]["tenant_id"] == "unit-tenant"
    assert calls[0]["actor"] == "unit-user"


def test_an_edited_pin_is_passed_through_as_sent(monkeypatch):
    client, calls = _client(monkeypatch, Role.STEWARD)
    response = client.post(
        "/store-dc/pins/confirm", json={"customer_id": 4, "site_label": "S1", "latitude": -26.1, "longitude": 28.0}
    )
    assert response.status_code == 200
    assert calls[0]["items"][0]["latitude"] == -26.1 and calls[0]["items"][0]["longitude"] == 28.0


def test_a_single_confirm_that_cannot_be_saved_is_an_error_not_a_success(monkeypatch):
    failed = {"saved": [], "failed": [{"customer_id": 4, "site_label": "S1", "error": "No proposal for this store; send coordinates"}]}
    client, _ = _client(monkeypatch, Role.STEWARD, failed)
    response = client.post("/store-dc/pins/confirm", json={"customer_id": 4, "site_label": "S1"})
    assert response.status_code == 400
    assert "No proposal" in response.json()["detail"]
    missing = {"saved": [], "failed": [{"customer_id": 4, "site_label": "S1", "error": "Store not found for this customer"}]}
    client, _ = _client(monkeypatch, Role.STEWARD, missing)
    assert client.post("/store-dc/pins/confirm", json={"customer_id": 4, "site_label": "S1"}).status_code == 404


def test_bulk_confirm_returns_saved_and_failed(monkeypatch):
    result = {
        "saved": [{"site_label": "S1", "pinned": True}],
        "failed": [{"customer_id": 4, "site_label": "S2", "error": "No proposal for this store; send coordinates"}],
    }
    client, calls = _client(monkeypatch, Role.STEWARD, result)
    response = client.post(
        "/store-dc/pins/confirm-bulk",
        json={"pins": [{"customer_id": 4, "site_label": "S1"}, {"customer_id": 4, "site_label": "S2"}]},
    )
    assert response.status_code == 200
    assert response.json() == result
    assert [item["site_label"] for item in calls[0]["items"]] == ["S1", "S2"]


def test_bulk_confirm_refuses_an_empty_or_oversized_request(monkeypatch):
    client, calls = _client(monkeypatch, Role.STEWARD)
    assert client.post("/store-dc/pins/confirm-bulk", json={"pins": []}).status_code == 422
    too_many = [{"customer_id": 1, "site_label": f"S{i}"} for i in range(endpoint.MAX_BULK_CONFIRM + 1)]
    assert client.post("/store-dc/pins/confirm-bulk", json={"pins": too_many}).status_code == 422
    assert calls == []


def test_the_confirm_routes_are_not_get_routes_so_a_read_never_writes():
    for route in endpoint.router.routes:
        if route.path.startswith("/pins"):
            assert route.methods == {"POST"}
