"""Unit tests for derived channel stock (no DB — ALLOW_TESTS_ON_DEV_DB unset)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.channel_ops_derived_stock import (
    VARIANCE_FLAG_PCT,
    VELOCITY_WINDOW_DAYS,
    compute_derived_stock,
    compute_snapshot_variance,
    replenishment_flag_v1,
    velocity_method_for_days,
    velocity_window_days_used,
    weekly_velocity_from_units,
    weeks_of_cover_or_none,
    yoy_pct_or_none,
)


def test_derived_stock_basic_arithmetic() -> None:
    # 100 reported − 30 sell-out + 20 landed = 90
    assert compute_derived_stock(
        reported_soh=100, sell_out_since=30, landed_since=20
    ) == Decimal("90")


def test_derived_stock_zero_movements() -> None:
    assert compute_derived_stock(
        reported_soh=50, sell_out_since=0, landed_since=0
    ) == Decimal("50")


def test_derived_stock_can_go_negative() -> None:
    # Over-sell relative to snapshot is visible, not clamped.
    assert compute_derived_stock(
        reported_soh=10, sell_out_since=40, landed_since=5
    ) == Decimal("-25")


def test_variance_flag_within_band() -> None:
    # 5% drift → not flagged at 10% threshold
    var, pct, flagged = compute_snapshot_variance(
        reported_next=105, predicted_at_next=100, flag_pct=VARIANCE_FLAG_PCT
    )
    assert var == Decimal("5")
    assert pct == Decimal("0.05")
    assert flagged is False


def test_variance_flag_above_band() -> None:
    var, pct, flagged = compute_snapshot_variance(
        reported_next=120, predicted_at_next=100, flag_pct=VARIANCE_FLAG_PCT
    )
    assert var == Decimal("20")
    assert pct == Decimal("0.2")
    assert flagged is True


def test_variance_flag_zero_predicted_nonzero_reported() -> None:
    var, pct, flagged = compute_snapshot_variance(
        reported_next=5, predicted_at_next=0
    )
    assert var == Decimal("5")
    assert pct is None
    assert flagged is True


def test_variance_flag_zero_both() -> None:
    var, pct, flagged = compute_snapshot_variance(
        reported_next=0, predicted_at_next=0
    )
    assert var == Decimal("0")
    assert pct is None
    assert flagged is False


def test_weeks_of_cover_normal() -> None:
    assert weeks_of_cover_or_none(100, 10) == 10.0


def test_weeks_of_cover_near_zero_velocity_is_none() -> None:
    assert weeks_of_cover_or_none(100, 0) is None
    assert weeks_of_cover_or_none(100, 0.005) is None
    assert weeks_of_cover_or_none(100, None) is None
    assert weeks_of_cover_or_none(None, 10) is None


def test_replenishment_flag_v1_default_four_weeks() -> None:
    assert replenishment_flag_v1(3.9) is True
    assert replenishment_flag_v1(4.0) is False
    assert replenishment_flag_v1(0) is False
    assert replenishment_flag_v1(None) is False
    assert replenishment_flag_v1(2.0, threshold_weeks=2.0) is False
    assert replenishment_flag_v1(1.5, threshold_weeks=2.0) is True


def test_yoy_pct_denominator_guard() -> None:
    assert yoy_pct_or_none(110, 100) == 0.1
    assert yoy_pct_or_none(50, 0) is None
    assert yoy_pct_or_none(50, None) is None
    assert yoy_pct_or_none(None, 100) is None
    assert yoy_pct_or_none(50, -10) is None


def test_snapshot_boundary_semantics_documented() -> None:
    """Sell-out and landed use strict > snapshot_date (not >=).

    Pure arithmetic check: movements on the snapshot day itself are excluded
    from the delta (they belong to the reported snapshot).
    """
    # If someone incorrectly included same-day sell-out of 5, derived would be 95.
    # Correct: only post-snapshot movements → 100 − 0 + 0 = 100 when same-day ignored.
    assert compute_derived_stock(
        reported_soh=100, sell_out_since=0, landed_since=0
    ) == Decimal("100")
    # And post-snapshot sell-out of 5 → 95
    assert compute_derived_stock(
        reported_soh=100, sell_out_since=5, landed_since=0
    ) == Decimal("95")


def test_pipeline_open_order_exclusion_is_caller_contract() -> None:
    """Landed units passed in must already exclude pipeline/open_order.

    The pure function trusts landed_since; SQL filter enforces line_state=shipped.
    """
    # If pipeline leaked 50 into landed_since, derived would inflate — callers must not.
    assert compute_derived_stock(
        reported_soh=100, sell_out_since=0, landed_since=0
    ) == Decimal("100")
    # Explicit shipped-only landed of 12
    assert compute_derived_stock(
        reported_soh=100, sell_out_since=0, landed_since=12
    ) == Decimal("112")


def test_date_ordering_for_variance_window() -> None:
    """Variance window is (prior, next] for sell-out and landed."""
    prior = date(2026, 1, 1)
    next_ = date(2026, 2, 1)
    assert prior < next_
    # Predicted from prior reported through next snapshot date
    predicted = compute_derived_stock(
        reported_soh=200, sell_out_since=40, landed_since=10
    )
    assert predicted == Decimal("170")
    _, _, flagged = compute_snapshot_variance(
        reported_next=170, predicted_at_next=predicted
    )
    assert flagged is False


def test_velocity_window_days_continuous_at_364() -> None:
    as_of = date(2026, 8, 17)
    first = as_of - timedelta(days=VELOCITY_WINDOW_DAYS)
    days = velocity_window_days_used(as_of=as_of, first_observation=first)
    assert days == 364
    assert velocity_method_for_days(days) == "a3_02_364_over_52"
    # 364 units over 364 days → weekly = 7; same as /52 of 364.
    assert weekly_velocity_from_units(364, days) == Decimal("7")
    assert weekly_velocity_from_units(364, 364) == Decimal("364") / Decimal("52")


def test_velocity_window_never_divides_short_history_by_52() -> None:
    as_of = date(2026, 8, 17)
    first = as_of - timedelta(days=90)
    days = velocity_window_days_used(as_of=as_of, first_observation=first)
    assert days == 90
    assert velocity_method_for_days(days) == "available_window_over_weeks"
    # 90 units in 90 days → weekly = 7, NOT 90/52 ≈ 1.73
    weekly = weekly_velocity_from_units(90, days)
    assert weekly == Decimal("7")
    assert weekly != Decimal("90") / Decimal("52")
