"""Unit tests for lineup-derived budget position (no historical budget facts)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.lineup.budget_position import (
    build_budget_position,
    derive_planned_reservations_from_lineup,
    derive_planned_reservations_with_diagnostics,
    normalize_period_label,
    period_label_sql_variants,
)


def test_normalize_period_label_variants():
    assert normalize_period_label("26Q2") == "2026Q2"
    assert normalize_period_label("2026 Q2") == "2026Q2"
    assert normalize_period_label("2026Q2") == "2026Q2"
    assert "26Q2" in period_label_sql_variants("2026Q2")
    assert "2026 Q2" in period_label_sql_variants("26Q2")


def test_derive_planned_reservations_from_fact_lineup(monkeypatch):
    item = SimpleNamespace(
        id=1,
        product_id=10,
        customer_id=20,
        planned_volume_units=100,
        period_label="26Q2",
    )
    # SKU has cost/reserve only — no target_srp_local (model truth).
    sku = SimpleNamespace(
        product_id=10,
        controlled_cost_amount=500.0,
        reserve_total_pct=0.1,
        promo_reserve_split_pct=0.5,
        vat_rate_pct=0.15,
        fx_plan_currency_per_cost_currency=1.0,
    )

    db = AsyncMock()
    db.scalars = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[item])),
            MagicMock(all=MagicMock(return_value=[sku])),
        ]
    )
    # SRP evidence from commercial lineup (dap preferred)
    db.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[(10, 1000.0, None, 99)]))
    )

    monkeypatch.setattr(
        "app.services.lineup.budget_position.compute_profit_with_reservation",
        lambda **kwargs: {
            "reservation": {"total": 42.5},
            "oem_sell_in_per_unit": 800.0,
        },
    )

    planned = asyncio.run(derive_planned_reservations_from_lineup(db, period_label="26Q2"))
    assert len(planned) == 1
    assert planned[0]["reserved_amount"] == 42.5
    assert planned[0]["product_id"] == 10
    assert planned[0]["revenue"] == 800.0 * 100
    assert planned[0]["target_srp_local"] == 1000.0
    assert planned[0]["srp_source"] == "commercial_lineup_evidence"


def test_derive_skips_missing_srp_without_fabricating(monkeypatch):
    item = SimpleNamespace(
        id=1,
        product_id=10,
        customer_id=20,
        planned_volume_units=100,
        period_label="26Q2",
    )
    sku = SimpleNamespace(
        product_id=10,
        controlled_cost_amount=500.0,
        reserve_total_pct=0.1,
        promo_reserve_split_pct=0.5,
        vat_rate_pct=0.15,
        fx_plan_currency_per_cost_currency=1.0,
    )

    db = AsyncMock()
    db.scalars = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[item])),
            MagicMock(all=MagicMock(return_value=[sku])),
        ]
    )
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    called = {"n": 0}

    def _boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("must not compute reservation without SRP")

    monkeypatch.setattr(
        "app.services.lineup.budget_position.compute_profit_with_reservation",
        _boom,
    )

    planned, diag = asyncio.run(
        derive_planned_reservations_with_diagnostics(db, period_label="26Q2")
    )
    assert planned == []
    assert diag["skipped_missing_srp"] == 1
    assert called["n"] == 0


def test_build_budget_position_auto_derives_when_planned_empty(monkeypatch):
    db = AsyncMock()

    async def _fake_derive(*_a, **_k):
        return [{"product_id": 1, "reserved_amount": 100.0, "revenue": 1000.0}], {
            "skipped_missing_sku": 0,
            "skipped_missing_srp": 0,
            "skipped_zero_qty": 0,
        }

    monkeypatch.setattr(
        "app.services.lineup.budget_position.derive_planned_reservations_with_diagnostics",
        _fake_derive,
    )

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(25.0, 400.0, 3))),
            MagicMock(scalar=MagicMock(return_value=2)),
        ]
    )

    out = asyncio.run(build_budget_position(db, period_label="26Q2"))
    assert out["planned_from_lineup_derived"] is True
    assert out["tracks"]["money"]["planned_reservation_usd"] == 100.0
    assert out["tracks"]["money"]["drawn_cpor_usd"] == 25.0
    assert out["tracks"]["money"]["status"] == "ok"
    assert out["cpor_line_count"] == 3
    assert out["period_label_normalized"] == "2026Q2"


def test_build_budget_position_missing_sku_economics(monkeypatch):
    db = AsyncMock()

    async def _fake_derive(*_a, **_k):
        return [], {
            "skipped_missing_sku": 0,
            "skipped_missing_srp": 0,
            "skipped_zero_qty": 0,
        }

    monkeypatch.setattr(
        "app.services.lineup.budget_position.derive_planned_reservations_with_diagnostics",
        _fake_derive,
    )

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(10.0, 100.0, 1))),
            MagicMock(scalar=MagicMock(return_value=0)),
        ]
    )

    out = asyncio.run(build_budget_position(db, period_label="2026Q2"))
    assert out["tracks"]["money"]["status"] == "missing_sku_economics"
    assert out["sku_assumption_count"] == 0


def test_build_budget_position_missing_srp_status(monkeypatch):
    db = AsyncMock()

    async def _fake_derive(*_a, **_k):
        return [], {
            "skipped_missing_sku": 0,
            "skipped_missing_srp": 3,
            "skipped_zero_qty": 0,
        }

    monkeypatch.setattr(
        "app.services.lineup.budget_position.derive_planned_reservations_with_diagnostics",
        _fake_derive,
    )

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(0.0, 0.0, 0))),
            MagicMock(scalar=MagicMock(return_value=5)),
        ]
    )

    out = asyncio.run(build_budget_position(db, period_label="2026Q2"))
    assert out["tracks"]["money"]["status"] == "missing_srp"
    assert out["derive_diagnostics"]["skipped_missing_srp"] == 3
