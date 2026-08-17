"""Commercial tenant profile + budget-position payload alignment."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services import commercial_tenant_profile as profile
from app.services.lineup.budget_position import build_budget_position


def test_woc_profile_keys_roundtrip_and_clamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    saved = profile.save_tenant_profile_overrides(
        "acme",
        {"reporting_cadence": "weekly_tuesday", "woc_min_velocity_days": 12},
    )
    assert saved["reporting_cadence"] == "weekly_tuesday"
    assert saved["woc_min_velocity_days"] == 28  # clamp floor
    snap = profile.profile_snapshot("acme")
    assert snap["reporting_cadence"] == "weekly_tuesday"
    assert snap["woc_min_velocity_days"] == 28
    saved_hi = profile.save_tenant_profile_overrides("acme", {"woc_min_velocity_days": 400})
    assert saved_hi["woc_min_velocity_days"] == 90


def test_default_woc_profile_is_weekly_monday_90() -> None:
    snap = profile.profile_snapshot()
    assert snap["reporting_cadence"] == "weekly_monday"
    assert snap["woc_min_velocity_days"] == 90
    snap = profile.profile_snapshot()
    assert snap["constraint_axis"] == "money"
    assert snap["over_budget_action"] == "require_reapproval"
    assert snap["reservation_source"] == "derived_from_profit"
    assert snap["pm_attribution_mode"] == "business_line"
    assert snap["hard_enforce_budget"] is True
    assert "money_ceiling_usd" in snap
    assert snap["support_norms_trailing_quarters"] == 4


def test_budget_position_payload_uses_profile():
    db = AsyncMock()

    async def _execute(stmt):
        # first call = cpor sums; second = sku count
        result = MagicMock()
        result.one.return_value = (100.0, 1800.0, 3)
        result.scalar.return_value = 0
        return result

    db.execute = AsyncMock(side_effect=_execute)

    out = asyncio.run(
        build_budget_position(
            db,
            planned_reservations=[{"reserved_amount": 50.0, "revenue": 500.0}],
        )
    )
    assert out["binding_axis"] == "money"
    assert out["constraint_type"] == "money"
    assert out["over_budget_action"] == "require_reapproval"
    assert out["reservation_source"] == "derived_from_profit"
    assert out["q002_reservation_source"] == "derived_from_profit"
    assert out["hard_enforce"] is True
    assert out["tracks"]["money"]["binding"] is True
    assert out["tracks"]["support_pct"]["binding"] is False
    assert out["tracks"]["money"]["status"] == "over"
