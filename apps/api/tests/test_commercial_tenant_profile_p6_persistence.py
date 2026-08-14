"""BACKLOG-096 (P6) — tenant profile file-persistence overrides (no DB)."""

from __future__ import annotations

import pytest

from app.services import commercial_tenant_profile as profile


@pytest.fixture(autouse=True)
def _isolate_tenant_profiles_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    yield


def test_load_overrides_missing_file_returns_empty() -> None:
    assert profile.load_tenant_profile_overrides("acme") == {}


def test_save_then_load_roundtrip() -> None:
    saved = profile.save_tenant_profile_overrides(
        "acme", {"constraint_axis": "support_pct", "over_budget_action": "warn"}
    )
    assert saved == {"constraint_axis": "support_pct", "over_budget_action": "warn"}
    loaded = profile.load_tenant_profile_overrides("acme")
    assert loaded == saved


def test_save_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="constraint_axis"):
        profile.save_tenant_profile_overrides("acme", {"constraint_axis": "not_a_real_axis"})


def test_save_drops_unknown_keys_and_empty_values() -> None:
    saved = profile.save_tenant_profile_overrides(
        "acme",
        {"constraint_axis": "money", "not_a_real_key": "x", "over_budget_action": ""},
    )
    assert saved == {"constraint_axis": "money"}


def test_profile_snapshot_merges_overrides_over_defaults() -> None:
    baseline = profile.profile_snapshot("no-override-tenant")
    assert baseline["constraint_axis"] == profile.CONSTRAINT_AXIS
    assert baseline["overrides_present"] == []

    profile.save_tenant_profile_overrides("acme", {"pm_attribution_mode": "none"})
    snap = profile.profile_snapshot("acme")
    assert snap["pm_attribution_mode"] == "none"
    assert snap["constraint_axis"] == profile.CONSTRAINT_AXIS  # unset key falls back to default
    assert snap["overrides_present"] == ["pm_attribution_mode"]
    assert snap["tenant_id"] == "acme"


def test_tenant_id_sanitized_for_filesystem_safety() -> None:
    path = profile._tenant_profile_override_path("../../etc/passwd")
    assert path.name == "etcpasswd.json"
    assert ".." not in str(path)


def test_default_tenant_profile_snapshot_backward_compatible() -> None:
    # Existing call sites call profile_snapshot() with no args.
    snap = profile.profile_snapshot()
    assert snap["tenant_id"] == "default"
    assert snap["constraint_axis"] == profile.CONSTRAINT_AXIS
    assert snap["lineup_export_columns"][0]["field"] == "customer_code"
    assert snap["lineup_export_columns"][0]["header"] == "Customer Code"


def test_lineup_export_columns_roundtrip_and_reject_unknown_field() -> None:
    saved = profile.save_tenant_profile_overrides(
        "acme",
        {
            "lineup_export_columns": [
                {"field": "sku", "header": "Part"},
                {"field": "planned_qty", "header": "Volume"},
            ]
        },
    )
    assert saved["lineup_export_columns"][0] == {"field": "sku", "header": "Part"}
    loaded = profile.load_tenant_profile_overrides("acme")
    assert loaded["lineup_export_columns"][1]["header"] == "Volume"
    snap = profile.profile_snapshot("acme")
    assert snap["lineup_export_columns"][0]["header"] == "Part"
    with pytest.raises(ValueError, match="unknown"):
        profile.save_tenant_profile_overrides(
            "acme",
            {"lineup_export_columns": [{"field": "not_a_field", "header": "X"}]},
        )
