"""Unit tests for BACKLOG-089 incremental unit cost (FLAG when baseline weak)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.incremental_unit_cost import evaluate_case_incremental_cost


def test_no_customer_insufficient() -> None:
    case = SimpleNamespace(
        id=1,
        case_code="C",
        customer_id=None,
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 14),
    )
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    out = evaluate_case_incremental_cost(session, case)
    assert out["baseline_status"] == "insufficient"
    assert out["cost_per_incremental_unit_usd"] is None


def test_insufficient_obs_flags_null(monkeypatch) -> None:
    case = SimpleNamespace(
        id=2,
        case_code="C2",
        customer_id=20,
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 14),
    )
    line = SimpleNamespace(id=10, product_id=100, ttl_support_usd=1000.0, ttl_support=18000.0, result_qty=50.0)
    session = MagicMock()
    session.scalars.return_value.all.return_value = [line]
    session.execute.return_value.all.return_value = [(10.0,)]  # obs=1 < min 3

    out = evaluate_case_incremental_cost(session, case)
    assert out["baseline_status"] == "insufficient"
    assert out["cost_per_incremental_unit_usd"] is None
    assert "FLAG" in out["message"] or "null" in out["message"].lower()


def test_ok_when_lift_positive(monkeypatch) -> None:
    case = SimpleNamespace(
        id=3,
        case_code="C3",
        customer_id=20,
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 14),  # 14 days
    )
    line = SimpleNamespace(id=11, product_id=100, ttl_support_usd=500.0, ttl_support=9000.0, result_qty=100.0)
    session = MagicMock()
    session.scalars.return_value.all.return_value = [line]
    # 5 weeks summing to 60 → lookback_units=60; scale 14/84; baseline=10; lift=90
    session.execute.return_value.all.return_value = [(12.0,), (12.0,), (12.0,), (12.0,), (12.0,)]

    out = evaluate_case_incremental_cost(session, case)
    assert out["baseline_status"] == "ok"
    assert out["lift_qty"] == 100.0 - 60.0 * (14 / 84)
    assert out["cost_per_incremental_unit_usd"] is not None
    assert abs(float(out["cost_per_incremental_unit_usd"]) - (500.0 / out["lift_qty"])) < 1e-6


def test_comparable_median_scales_median_week(monkeypatch) -> None:
    monkeypatch.setenv("CIP_INCREMENTAL_BASELINE_METHOD", "comparable_median")
    case = SimpleNamespace(
        id=4,
        case_code="C4",
        customer_id=20,
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 14),
    )
    line = SimpleNamespace(id=12, product_id=100, ttl_support_usd=200.0, ttl_support=0.0, result_qty=50.0)
    session = MagicMock()
    session.scalars.return_value.all.return_value = [line]
    session.execute.return_value.all.return_value = [(10.0,), (20.0,), (30.0,)]  # median 20

    out = evaluate_case_incremental_cost(session, case)
    assert out["line_baselines"][0]["median_week_units"] == 20.0
    expected_baseline = 20.0 * (14 / 7)
    assert abs(float(out["baseline_qty"]) - expected_baseline) < 1e-9
    assert out["baseline_status"] == "ok"
