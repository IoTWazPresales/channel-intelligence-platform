"""Unit tests for CPOR U4.6 CST channel intelligence read-model (no DB)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.channel_intelligence.cst_read_model import (
    GRAIN_POLICY,
    PeriodObs,
    build_observations,
    classify_trend,
    compute_entity_metrics,
    load_cst_read_model,
    sum_weekly_equiv_in_window,
    velocity_units_per_week,
)


def _obs(start: date, units: float, *, soh: float | None = None, price: float | None = None, pt: str = "weekly"):
    return PeriodObs(
        period_start=start,
        period_type=pt,
        units_sold=Decimal(str(units)),
        reported_soh=Decimal(str(soh)) if soh is not None else None,
        unit_sell_price=Decimal(str(price)) if price is not None else None,
        weekly_equiv_units=Decimal(str(units)) if not pt.startswith("month") else Decimal(str(units)) / Decimal("4.345"),
    )


def test_velocity_4wk_window() -> None:
    # 4 weeks × 10 units = 40 → velocity 10/wk
    obs = [_obs(date(2026, 1, d), 10) for d in (6, 13, 20, 27)]
    s, n = sum_weekly_equiv_in_window(obs, as_of=date(2026, 1, 27), window_weeks=4)
    assert n == 4
    assert float(velocity_units_per_week(s, 4)) == 10.0


def test_woc_null_when_velocity_near_zero() -> None:
    obs = [_obs(date(2026, 1, d), 0, soh=50, price=999) for d in (6, 13, 20, 27)]
    m = compute_entity_metrics(obs, as_of=date(2026, 1, 27), min_observed_weeks=4)
    assert m["data_state"] == "ok"
    assert m["weeks_of_cover"] is None
    assert m["weeks_of_cover_reason"] == "velocity_near_zero"
    assert m["aged_dead_stock"] is True
    assert m["aged_factors"]["unit_sell_price"] == 999.0
    assert "not selling" in m["aged_factors"]["interpretation"]


def test_insufficient_data_below_threshold() -> None:
    obs = [_obs(date(2026, 1, 6), 5, soh=10)]
    m = compute_entity_metrics(obs, as_of=date(2026, 1, 6), min_observed_weeks=4)
    assert m["data_state"] == "insufficient_data"
    assert m["aged_dead_stock"] is False
    assert m["weeks_of_cover"] is None


def test_trend_rising_falling_flat() -> None:
    assert classify_trend(Decimal("20"), Decimal("10")) == "rising"
    assert classify_trend(Decimal("10"), Decimal("20")) == "falling"
    assert classify_trend(Decimal("10.2"), Decimal("10")) == "flat"


def test_monthly_normalized_to_weekly() -> None:
    # 43.45 monthly units → 10 weekly-equiv
    row = SimpleNamespace(
        period_start_date=date(2026, 1, 1),
        period_type="monthly",
        units_sold=43.45,
        reported_soh=100,
        unit_sell_price=50,
    )
    obs = build_observations([row])
    assert len(obs) == 1
    assert abs(float(obs[0].weekly_equiv_units) - 10.0) < 0.01
    m = compute_entity_metrics(obs, as_of=date(2026, 1, 31), min_observed_weeks=1)
    assert m["grain_policy"] == GRAIN_POLICY
    assert m["data_state"] == "ok"


def test_empty_load_data_unavailable() -> None:
    session = MagicMock()
    session.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    out = load_cst_read_model(session)
    assert out["data_unavailable"] is True
    assert out["items"] == []


def test_load_groups_by_site() -> None:
    session = MagicMock()
    rows = [
        SimpleNamespace(
            customer_id=1,
            product_id=2,
            site_label="Store A",
            period_start_date=date(2026, 1, d),
            period_type="weekly",
            units_sold=5,
            reported_soh=20,
            unit_sell_price=100,
        )
        for d in (6, 13, 20, 27)
    ]
    session.scalars.return_value = MagicMock(all=MagicMock(return_value=rows))
    out = load_cst_read_model(session, min_observed_weeks=4)
    assert out["data_unavailable"] is False
    assert out["total"] == 1
    assert out["items"][0]["site_label"] == "Store A"
    assert out["items"][0]["data_state"] == "ok"
    assert out["items"][0]["velocity_4wk"] == 5.0
