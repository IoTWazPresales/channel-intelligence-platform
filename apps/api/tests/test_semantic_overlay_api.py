"""P3-1 U3 — GET/PUT /semantics/overlay (admin persist, default tenant)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import Role, get_current_user, get_optional_current_user
from app.main import app
from app.query.types import HandlerResult
from app.semantics.registry import catalog_for_tenant, clear_catalog_cache
from app.services import commercial_tenant_profile as profile

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_tenant_profiles_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    clear_catalog_cache()
    yield
    clear_catalog_cache()
    app.dependency_overrides.clear()


def _stub_user(role: Role = Role.ADMIN):
    async def _fake_user():
        return {
            "id": "test-user",
            "role": role,
            "tenant_id": "default",
            "email": None,
            "display_name": None,
        }

    return _fake_user


def test_overlay_get_returns_base_metrics_with_locked_formula() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.get("/api/v1/semantics/overlay")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "default"
    assert body["compose_ops"] == ["ratio", "alias"]
    fill = next(m for m in body["base_metrics"] if m["key"] == "fill_rate")
    assert fill["handler_backed"] is True
    assert fill["fact_family"] == "a1"
    assert "Σ min(shipped, planned)" in fill["locked"]["formula"]
    assert fill["locked"]["owner_surface"] == "plan-vs-executed"


def test_overlay_put_admin_relabel_hide_compose_on_default() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    app.dependency_overrides[get_optional_current_user] = _stub_user(Role.VIEWER)
    r = client.put(
        "/api/v1/semantics/overlay",
        json={
            "metrics": {
                "fill_rate": {"label": "On-time fill"},
                "claim_rate": {"hidden": True},
            },
            "composed": {
                "fill_vs_hit": {
                    "label": "Fill vs line-hit",
                    "compose": {
                        "op": "ratio",
                        "inputs": ["fill_rate", "line_hit_rate"],
                        "grain": ["period"],
                    },
                }
            },
        },
    )
    assert r.status_code == 200, r.text
    cat = catalog_for_tenant("default")
    assert cat.metric_by_key("fill_rate").label == "On-time fill"
    assert "Σ min(shipped, planned)" in cat.metric_by_key("fill_rate").formula
    assert cat.metric_by_key("claim_rate").hidden is True
    assert cat.metric_by_key("fill_vs_hit").compose.op == "ratio"

    listed = client.get("/api/v1/semantics/catalog")
    assert listed.status_code == 200
    keys = {m["key"]: m for m in listed.json()["metrics"]}
    assert keys["fill_rate"]["label"] == "On-time fill"
    assert "claim_rate" not in keys
    assert keys["fill_vs_hit"]["compose"]["op"] == "ratio"


@pytest.mark.anyio
async def test_overlay_put_composed_execute_returns_one_number() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.put(
        "/api/v1/semantics/overlay",
        json={
            "composed": {
                "fill_vs_hit": {
                    "label": "Fill vs line-hit",
                    "compose": {
                        "op": "ratio",
                        "inputs": ["fill_rate", "line_hit_rate"],
                        "grain": ["period"],
                    },
                }
            }
        },
    )
    assert r.status_code == 200, r.text

    async def _scalars(db, req, *, metric_key, explain_only=False):
        return (
            "a1_pve",
            HandlerResult(status="ok", value=0.80 if metric_key == "fill_rate" else 0.40),
        )

    from app.query.engine import execute_query

    with patch("app.query.compose.dispatch_handler", new=_scalars):
        result = await execute_query(
            AsyncMock(), metric="fill_vs_hit", grains=["period"], tenant_id="default"
        )
    assert result.ok is True
    assert result.handler == "composed"
    assert result.value == pytest.approx(2.0)


def test_overlay_put_viewer_and_steward_forbidden() -> None:
    app.dependency_overrides[get_current_user] = _stub_user(Role.VIEWER)
    r = client.put("/api/v1/semantics/overlay", json={"metrics": {"fill_rate": {"label": "Nope"}}})
    assert r.status_code == 403
    app.dependency_overrides[get_current_user] = _stub_user(Role.STEWARD)
    r2 = client.put("/api/v1/semantics/overlay", json={"metrics": {"fill_rate": {"label": "Nope"}}})
    assert r2.status_code == 403


def test_overlay_put_invalid_body_400() -> None:
    app.dependency_overrides[get_current_user] = _stub_user()
    r = client.put(
        "/api/v1/semantics/overlay",
        json={
            "composed": {
                "bad": {
                    "label": "Bad",
                    "compose": {
                        "op": "weighted_sum",
                        "inputs": ["fill_rate", "line_hit_rate"],
                        "grain": ["period"],
                    },
                }
            }
        },
    )
    assert r.status_code == 400
    assert "ratio and alias" in r.json()["detail"]
