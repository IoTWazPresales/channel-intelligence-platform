"""N-0110: customer stock gap arithmetic (no database)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.channel_intelligence.customer_stock_gap import (
    Receipt,
    ReportPeriod,
    compute_positions,
    gap_reason,
    grain_of,
    is_highlighted,
)

D = Decimal


def _week(start: date, *, units: str, on_hand: str | None, product: int = 1, in_transit: str | None = None):
    from app.services.imports.parsers.customer_sell_through_grain import period_end

    return ReportPeriod(
        product_id=product,
        grain="week",
        start=start,
        end=period_end(start, "week"),
        units_sold=D(units),
        on_hand=D(on_hand) if on_hand is not None else None,
        in_transit=D(in_transit) if in_transit is not None else None,
    )


def test_first_report_is_not_compared() -> None:
    out = compute_positions([_week(date(2026, 7, 6), units="5", on_hand="40")], [])
    assert len(out) == 1
    assert out[0].status == "first_report"
    assert out[0].expected is None and out[0].gap is None


def test_expected_is_previous_plus_matched_receipts_minus_units_sold() -> None:
    periods = [
        _week(date(2026, 7, 6), units="5", on_hand="40"),
        _week(date(2026, 7, 13), units="8", on_hand="50"),
    ]
    receipts = [Receipt(product_id=1, pod_date=date(2026, 7, 15), units=D("20"))]
    out = compute_positions(periods, receipts)
    second = out[1]
    assert second.status == "compared"
    assert second.previous_on_hand == D("40")
    assert second.receipts == D("20")
    assert second.units_sold_since == D("8")
    assert second.expected == D("52")  # 40 + 20 - 8
    assert second.gap == D("-2")  # 50 - 52: short


def test_receipt_on_or_before_previous_report_end_is_not_counted_again() -> None:
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="10"),
        _week(date(2026, 7, 13), units="0", on_hand="10"),
    ]
    # 2026-07-12 is the previous report's last day: already inside its on-hand.
    receipts = [Receipt(product_id=1, pod_date=date(2026, 7, 12), units=D("7"))]
    out = compute_positions(periods, receipts)
    assert out[1].receipts == D("0")
    assert out[1].gap == D("0")


def test_week_without_on_hand_restarts_the_chain() -> None:
    """N-0111 (Warren 2026-10-16): a week with no reported on-hand does not break the chain.

    The week is named (no_on_hand, its units kept) and the next on-hand restarts the chain:
    it is not compared with the report before the gap.
    """
    periods = [
        _week(date(2026, 7, 6), units="1", on_hand="30"),
        _week(date(2026, 7, 13), units="4", on_hand=None),  # sales-only upload
        _week(date(2026, 7, 20), units="6", on_hand="20"),
        _week(date(2026, 7, 27), units="5", on_hand="15"),
    ]
    out = compute_positions(periods, [])
    assert [p.status for p in out] == ["first_report", "no_on_hand", "chain_restart", "compared"]
    gap_week = out[1]
    assert (gap_week.period.start, gap_week.period.end) == (date(2026, 7, 13), date(2026, 7, 19))
    assert gap_week.period.units_sold == D("4") and gap_week.period.on_hand is None
    assert gap_week.gap is None
    assert out[2].gap is None and out[2].expected is None
    assert out[3].previous_on_hand == D("20")
    assert out[3].expected == D("15") and out[3].gap == D("0")


def test_missing_weeks_with_no_report_at_all_are_each_named() -> None:
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="10"),
        _week(date(2026, 8, 3), units="0", on_hand="10"),
    ]
    out = compute_positions(periods, [])
    assert [p.status for p in out] == ["first_report", "no_on_hand", "no_on_hand", "no_on_hand", "chain_restart"]
    assert [p.period.start for p in out if p.status == "no_on_hand"] == [
        date(2026, 7, 13),
        date(2026, 7, 20),
        date(2026, 7, 27),
    ]


def test_day_lines_inside_contiguous_weeks_keep_the_chain() -> None:
    """Day-dated sales roll into their Monday-Sunday week; weekly on-hand stays one chain."""
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="30"),
        ReportPeriod(product_id=1, grain="day", start=date(2026, 7, 14), end=date(2026, 7, 14), units_sold=D("3")),
        ReportPeriod(product_id=1, grain="day", start=date(2026, 7, 17), end=date(2026, 7, 17), units_sold=D("2")),
        _week(date(2026, 7, 13), units="0", on_hand="25"),
    ]
    out = compute_positions(periods, [])
    assert [p.status for p in out] == ["first_report", "compared"]
    assert out[1].units_sold_since == D("5") and out[1].gap == D("0")


def test_month_on_hand_reports_touch_and_compare() -> None:
    periods = [
        ReportPeriod(product_id=1, grain="month", start=date(2026, 6, 1), end=date(2026, 6, 30), on_hand=D("10")),
        ReportPeriod(product_id=1, grain="month", start=date(2026, 7, 1), end=date(2026, 7, 31), on_hand=D("10")),
    ]
    assert [p.status for p in compute_positions(periods, [])] == ["first_report", "compared"]


def test_surplus_and_products_are_independent() -> None:
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="5", product=1),
        _week(date(2026, 7, 13), units="0", on_hand="9", product=1),
        _week(date(2026, 7, 6), units="0", on_hand="5", product=2),
        _week(date(2026, 7, 13), units="0", on_hand="5", product=2),
    ]
    receipts = [Receipt(product_id=2, pod_date=date(2026, 7, 14), units=D("3"))]
    out = {(p.period.product_id, p.status): p for p in compute_positions(periods, receipts)}
    assert out[(1, "compared")].gap == D("4")  # over: a receipt CIP does not have
    assert out[(2, "compared")].gap == D("-3")  # short: delivered 3, report shows none


def test_in_transit_is_not_added_into_on_hand() -> None:
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="10"),
        _week(date(2026, 7, 13), units="0", on_hand="10", in_transit="5"),
    ]
    out = compute_positions(periods, [])
    assert out[1].expected == D("10")
    assert out[1].gap == D("0")


def test_reason_words_and_in_transit_hint() -> None:
    assert gap_reason(None).startswith("First report")
    assert gap_reason(0) == "Matches the expected position."
    assert gap_reason(-4, in_transit=3).startswith("Short: stock not delivered, lost, or sold outside the file.")
    assert "3 in transit may explain part of it" in gap_reason(-4, in_transit=3)
    assert gap_reason(2).startswith("Over: a receipt CIP does not have, a return, or overlapping periods")


def test_highlight_uses_absolute_units_not_percent() -> None:
    assert is_highlighted(-5, 5) is True
    assert is_highlighted(5, 5) is True
    assert is_highlighted(4.99, 5) is False
    assert is_highlighted(None, 1) is False
    # A 1 unit gap on 1000 units is 0.1 percent, still highlighted at a 1 unit threshold.
    assert is_highlighted(1, 1) is True


def test_grain_of_legacy_rows() -> None:
    assert grain_of(None, "weekly") == "week"
    assert grain_of(None, "monthly") == "month"
    assert grain_of(None, "daily") == "day"
    assert grain_of("day", "weekly") == "day"
