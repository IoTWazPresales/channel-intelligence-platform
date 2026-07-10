"""Unit tests for derived channel stock (no DB — ALLOW_TESTS_ON_DEV_DB unset)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.channel_ops_derived_stock import (
    VARIANCE_FLAG_PCT,
    compute_derived_stock,
    compute_snapshot_variance,
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
