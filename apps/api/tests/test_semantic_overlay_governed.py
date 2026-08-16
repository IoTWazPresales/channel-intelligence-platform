"""P3-1 U1 — governed semantic overlay from tenant_profiles/{id}.json (no migration)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.security import Role, get_optional_current_user
from app.main import app
from app.semantics.registry import (
    catalog_for_tenant,
    clear_catalog_cache,
    default_catalog,
    validate_metric_grain,
)
from app.services import commercial_tenant_profile as profile

FILL_RATE_FORMULA = (
    "Σ min(shipped, planned) / Σ planned on in-plan rows; shipped = line_state=shipped only"
)
FILL_RATE_FACTS = ("lineup_plan_qty", "linked_po_shipped_qty")
FILL_RATE_OWNER = "plan-vs-executed"


@pytest.fixture(autouse=True)
def _isolate_tenant_profiles_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    clear_catalog_cache()
    yield
    clear_catalog_cache()


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


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


def _fill(cat=None):
    catalog = cat or catalog_for_tenant("default")
    metric = catalog.metric_by_key("fill_rate")
    assert metric is not None
    return metric


def test_relabel_fill_rate_on_default_leaves_formula_untouched() -> None:
    platform = default_catalog().metric_by_key("fill_rate")
    assert platform is not None
    profile.save_tenant_profile_overrides(
        "default",
        {"semantic_overlay": {"metrics": {"fill_rate": {"label": "On-time fill"}}}},
    )
    cat = catalog_for_tenant("default")
    fill = _fill(cat)
    assert cat.overlay_applied is True
    assert fill.label == "On-time fill"
    assert fill.formula == FILL_RATE_FORMULA
    assert platform.formula == FILL_RATE_FORMULA
    assert tuple(fill.source_facts) == FILL_RATE_FACTS
    assert fill.owner_surface == FILL_RATE_OWNER
    assert cat.version != default_catalog().version

    client = TestClient(app)
    app.dependency_overrides[get_optional_current_user] = _stub_optional_user(Role.VIEWER)
    body = client.get("/api/v1/semantics/catalog").json()
    fill_row = next(m for m in body["metrics"] if m["key"] == "fill_rate")
    assert fill_row["label"] == "On-time fill"
    assert fill_row["formula"] == FILL_RATE_FORMULA
    assert fill_row["source_facts"] == list(FILL_RATE_FACTS)


def test_overlay_cannot_rewrite_formula_source_facts_owner_surface() -> None:
    profile.save_tenant_profile_overrides(
        "default",
        {
            "semantic_overlay": {
                "metrics": {
                    "fill_rate": {
                        "label": "Still fill",
                        "formula": "forged",
                        "source_facts": ["forged_fact"],
                        "owner_surface": "shipping",
                    }
                }
            }
        },
    )
    persisted = profile.semantic_overlay_for_tenant("default")
    assert "formula" not in persisted["metrics"]["fill_rate"]
    assert "source_facts" not in persisted["metrics"]["fill_rate"]
    assert "owner_surface" not in persisted["metrics"]["fill_rate"]
    fill = _fill()
    assert fill.label == "Still fill"
    assert fill.formula == FILL_RATE_FORMULA
    assert tuple(fill.source_facts) == FILL_RATE_FACTS
    assert fill.owner_surface == FILL_RATE_OWNER


def test_grain_restrict_fill_rate_to_period_only() -> None:
    profile.save_tenant_profile_overrides(
        "default",
        {
            "semantic_overlay": {
                "metrics": {"fill_rate": {"allowed_grains": [["period"]]}}
            }
        },
    )
    fill = _fill()
    assert fill.allowed_grains == (frozenset({"period"}),)
    ok = validate_metric_grain("fill_rate", ["period"], tenant_id="default")
    assert ok.ok is True
    refused = validate_metric_grain("fill_rate", ["period", "bu"], tenant_id="default")
    assert refused.ok is False
    # Platform catalog (no tenant overlay) still allows period×bu.
    platform = validate_metric_grain("fill_rate", ["period", "bu"])
    assert platform.ok is True


def test_grain_widen_rejected_on_save() -> None:
    with pytest.raises(ValueError, match="restrict only"):
        profile.save_tenant_profile_overrides(
            "default",
            {
                "semantic_overlay": {
                    "metrics": {
                        "fill_rate": {"allowed_grains": [["distributor", "product"]]}
                    }
                }
            },
        )
    assert profile.semantic_overlay_for_tenant("default")["metrics"] == {}
    fill = _fill()
    assert frozenset({"period", "bu"}) in fill.allowed_grains


def test_unknown_metric_rejected_on_save() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        profile.save_tenant_profile_overrides(
            "default",
            {"semantic_overlay": {"metrics": {"not_a_real_metric": {"label": "Nope"}}}},
        )


def test_hidden_omitted_from_metrics_listing_and_validate_refuses() -> None:
    profile.save_tenant_profile_overrides(
        "default",
        {"semantic_overlay": {"metrics": {"line_hit_rate": {"hidden": True}}}},
    )
    cat = catalog_for_tenant("default")
    hidden = cat.metric_by_key("line_hit_rate")
    assert hidden is not None
    assert hidden.hidden is True
    refused = validate_metric_grain("line_hit_rate", ["period"], tenant_id="default")
    assert refused.ok is False
    assert "hidden" in refused.message.lower()

    client = TestClient(app)
    app.dependency_overrides[get_optional_current_user] = _stub_optional_user(Role.VIEWER)
    listed = client.get("/api/v1/semantics/metrics")
    assert listed.status_code == 200
    keys = {m["key"] for m in listed.json()["metrics"]}
    assert "line_hit_rate" not in keys
    assert "fill_rate" in keys

    catalog = client.get("/api/v1/semantics/catalog")
    assert catalog.status_code == 200
    catalog_keys = {m["key"] for m in catalog.json()["metrics"]}
    assert "line_hit_rate" not in catalog_keys

    app.dependency_overrides[get_optional_current_user] = _stub_optional_user(Role.ADMIN)
    admin_metrics = client.get("/api/v1/semantics/metrics")
    assert admin_metrics.status_code == 200
    by_key = {m["key"]: m for m in admin_metrics.json()["metrics"]}
    assert by_key["line_hit_rate"]["hidden"] is True

    relabel = client.get("/api/v1/semantics/catalog")
    fill_row = next(m for m in relabel.json()["metrics"] if m["key"] == "fill_rate")
    assert fill_row["formula"] == FILL_RATE_FORMULA


def test_malformed_overlay_on_load_flag_not_block(tmp_path) -> None:
    path = tmp_path / "default.json"
    path.write_text(
        json.dumps(
            {
                "constraint_axis": "money",
                "semantic_overlay": {
                    "metrics": {
                        "fill_rate": {"label": "Kept", "allowed_grains": [["distributor"]]},
                        "line_hit_rate": {"label": "Hit (tenant)"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = profile.load_tenant_profile_overrides("default")
    assert loaded["constraint_axis"] == "money"
    overlay_metrics = loaded.get("semantic_overlay", {}).get("metrics", {})
    assert "fill_rate" not in overlay_metrics  # invalid grain drop whole key
    assert overlay_metrics["line_hit_rate"]["label"] == "Hit (tenant)"
    cat = catalog_for_tenant("default")
    assert _fill(cat).label == "Fill rate"
    assert cat.metric_by_key("line_hit_rate").label == "Hit (tenant)"


def test_overlay_save_merges_and_does_not_wipe_commercial_keys() -> None:
    profile.save_tenant_profile_overrides("default", {"constraint_axis": "support_pct"})
    profile.save_tenant_profile_overrides(
        "default",
        {"semantic_overlay": {"metrics": {"fill_rate": {"label": "Fill"}}}},
    )
    loaded = profile.load_tenant_profile_overrides("default")
    assert loaded["constraint_axis"] == "support_pct"
    assert loaded["semantic_overlay"]["metrics"]["fill_rate"]["label"] == "Fill"
