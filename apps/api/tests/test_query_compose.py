"""P3-1 U2 — intra-family composed metrics (ratio / alias) over handler-backed inputs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.security import Role, get_optional_current_user
from app.main import app
from app.query.cache import clear_query_cache
from app.query.engine import execute_query
from app.query.handlers import handler_name_for
from app.query.types import HandlerResult
from app.semantics.registry import catalog_for_tenant, clear_catalog_cache, validate_metric_grain
from app.services import commercial_tenant_profile as profile

FILL_VS_HIT = {
    "id": "T-FILL-VS-HIT",
    "key": "fill_vs_hit",
    "label": "Fill vs line-hit",
    "compose": {
        "op": "ratio",
        "inputs": ["fill_rate", "line_hit_rate"],
        "grain": ["period"],
    },
}


@pytest.fixture(autouse=True)
def _isolate_tenant_profiles_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    clear_catalog_cache()
    clear_query_cache()
    yield
    clear_catalog_cache()
    clear_query_cache()


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _save_ratio() -> None:
    profile.save_tenant_profile_overrides(
        "default",
        {"semantic_overlay": {"composed": {"fill_vs_hit": FILL_VS_HIT}}},
    )


def _stub_optional_user(role: Role = Role.ADMIN):
    async def _fake_user():
        return {
            "id": "test-user",
            "role": role,
            "tenant_id": "default",
            "email": None,
            "display_name": None,
        }

    return _fake_user


async def _fake_db():
    yield AsyncMock()


async def _dispatch_scalars(db, req, *, metric_key, explain_only=False):
    values = {"fill_rate": 0.80, "line_hit_rate": 0.40, "weeks_of_cover": 10.0}
    return (
        "a1_pve" if metric_key in {"fill_rate", "line_hit_rate"} else "a3_stock",
        HandlerResult(status="ok", value=values[metric_key], invariants_applied=["test_input"]),
    )


def test_ratio_rejected_cross_family_on_save() -> None:
    with pytest.raises(ValueError, match="fact family"):
        profile.save_tenant_profile_overrides(
            "default",
            {
                "semantic_overlay": {
                    "composed": {
                        "bad_mix": {
                            "label": "Bad mix",
                            "compose": {
                                "op": "ratio",
                                "inputs": ["fill_rate", "support_spend"],
                                "grain": ["period"],
                            },
                        }
                    }
                }
            },
        )


def test_weighted_sum_rejected_on_save() -> None:
    with pytest.raises(ValueError, match="ratio and alias"):
        profile.save_tenant_profile_overrides(
            "default",
            {
                "semantic_overlay": {
                    "composed": {
                        "weighted": {
                            "label": "Weighted",
                            "compose": {
                                "op": "weighted_sum",
                                "inputs": ["fill_rate", "line_hit_rate"],
                                "grain": ["period"],
                            },
                        }
                    }
                }
            },
        )


def test_alias_forbidden_grain_rejected_on_save() -> None:
    with pytest.raises(ValueError, match="not an allowed grain"):
        profile.save_tenant_profile_overrides(
            "default",
            {
                "semantic_overlay": {
                    "composed": {
                        "woc_period": {
                            "label": "WoC at period",
                            "compose": {
                                "op": "alias",
                                "inputs": ["weeks_of_cover"],
                                "grain": ["period"],
                            },
                        }
                    }
                }
            },
        )


def test_cannot_shadow_platform_metric_with_compose() -> None:
    with pytest.raises(ValueError, match="shadow"):
        profile.save_tenant_profile_overrides(
            "default",
            {
                "semantic_overlay": {
                    "metrics": {
                        "fill_rate": {
                            "label": "Hijack",
                            "compose": {
                                "op": "alias",
                                "inputs": ["line_hit_rate"],
                                "grain": ["period"],
                            },
                        }
                    }
                }
            },
        )


def test_composed_ratio_lands_in_default_catalog() -> None:
    _save_ratio()
    cat = catalog_for_tenant("default")
    metric = cat.metric_by_key("fill_vs_hit")
    assert metric is not None
    assert metric.compose is not None
    assert metric.compose.op == "ratio"
    assert metric.compose.inputs == ("fill_rate", "line_hit_rate")
    assert metric.formula == "fill_rate / line_hit_rate"
    assert metric.owner_surface == "plan-vs-executed"
    assert "lineup_plan_qty" in metric.source_facts
    assert handler_name_for("fill_vs_hit", catalog=cat) == "composed"
    assert handler_name_for("fill_rate", catalog=cat) == "a1_pve"
    ok = validate_metric_grain("fill_vs_hit", ["period"], tenant_id="default")
    assert ok.ok is True
    refused = validate_metric_grain("fill_vs_hit", ["period", "bu"], tenant_id="default")
    assert refused.ok is False
    fill = cat.metric_by_key("fill_rate")
    assert fill is not None
    assert "Σ min(shipped, planned)" in fill.formula


@pytest.mark.anyio
async def test_execute_ratio_one_number_matches_manual_num_den() -> None:
    _save_ratio()
    db = AsyncMock()
    with patch("app.query.compose.dispatch_handler", new=_dispatch_scalars):
        composed = await execute_query(db, metric="fill_vs_hit", grains=["period"], tenant_id="default")
    assert composed.ok is True
    assert composed.handler == "composed"
    assert composed.value == pytest.approx(0.80 / 0.40)
    assert composed.explain is not None
    input_keys = [row["key"] for row in composed.explain.get("inputs") or []]
    assert input_keys == ["fill_rate", "line_hit_rate"]


@pytest.mark.anyio
async def test_execute_ratio_denominator_zero_is_governed_null() -> None:
    _save_ratio()
    db = AsyncMock()

    async def _den_zero(db, req, *, metric_key, explain_only=False):
        val = 0.80 if metric_key == "fill_rate" else 0.0
        return ("a1_pve", HandlerResult(status="ok", value=val))

    with patch("app.query.compose.dispatch_handler", new=_den_zero):
        result = await execute_query(db, metric="fill_vs_hit", grains=["period"], tenant_id="default")
    assert result.status == "ok"
    assert result.value is None
    assert "denominator" in (result.message or "").lower()


@pytest.mark.anyio
async def test_execute_alias_passthrough() -> None:
    profile.save_tenant_profile_overrides(
        "default",
        {
            "semantic_overlay": {
                "composed": {
                    "fill_period": {
                        "label": "Fill (period)",
                        "compose": {"op": "alias", "inputs": ["fill_rate"], "grain": ["period"]},
                    }
                }
            }
        },
    )
    db = AsyncMock()
    with patch("app.query.compose.dispatch_handler", new=_dispatch_scalars):
        result = await execute_query(db, metric="fill_period", grains=["period"], tenant_id="default")
    assert result.ok is True
    assert result.handler == "composed"
    assert result.value == pytest.approx(0.80)
    assert result.explain is not None
    assert result.explain.get("op") == "alias"


@pytest.mark.anyio
async def test_composed_query_is_cached_then_invalidated_on_overlay_edit() -> None:
    _save_ratio()
    db = AsyncMock()
    calls: list[str] = []

    async def _counting(db, req, *, metric_key, explain_only=False):
        calls.append(metric_key)
        return await _dispatch_scalars(db, req, metric_key=metric_key, explain_only=explain_only)

    with patch("app.query.compose.dispatch_handler", new=_counting):
        r1 = await execute_query(db, metric="fill_vs_hit", grains=["period"], tenant_id="default")
        r2 = await execute_query(db, metric="fill_vs_hit", grains=["period"], tenant_id="default")
    assert r1.cache and r1.cache.hit is False
    assert r2.cache and r2.cache.hit is True
    assert r2.value == pytest.approx(2.0)
    assert calls == ["fill_rate", "line_hit_rate"]

    profile.save_tenant_profile_overrides(
        "default",
        {
            "semantic_overlay": {
                "composed": {
                    "fill_vs_hit": {**FILL_VS_HIT, "label": "Fill vs hit (renamed)"},
                }
            }
        },
    )
    with patch("app.query.compose.dispatch_handler", new=_counting):
        r3 = await execute_query(db, metric="fill_vs_hit", grains=["period"], tenant_id="default")
    assert r3.cache and r3.cache.hit is False
    assert r3.value == pytest.approx(2.0)
    renamed = catalog_for_tenant("default").metric_by_key("fill_vs_hit")
    assert renamed is not None
    assert renamed.label == "Fill vs hit (renamed)"


@pytest.mark.anyio
async def test_query_execute_endpoint_returns_composed_ratio() -> None:
    _save_ratio()
    app.dependency_overrides[get_optional_current_user] = _stub_optional_user()
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)
    with patch("app.query.compose.dispatch_handler", new=_dispatch_scalars):
        response = client.post(
            "/api/v1/query/execute",
            json={"metric": "fill_vs_hit", "grains": ["period"]},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["handler"] == "composed"
    assert body["value"] == pytest.approx(2.0)
    assert [row["key"] for row in (body.get("explain") or {}).get("inputs") or []] == [
        "fill_rate",
        "line_hit_rate",
    ]
