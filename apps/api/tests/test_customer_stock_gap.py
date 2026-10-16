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


def test_week_without_on_hand_but_with_sales_bridges_the_chain() -> None:
    """N-0111 (Warren 2026-10-16, corrects D-0105): a week with sales but no on-hand is bridged.

    The week is named (no_on_hand, its units kept, not compared) and the next on-hand is compared
    with the last reported on-hand minus all sales in between.
    """
    periods = [
        _week(date(2026, 7, 6), units="1", on_hand="30"),
        _week(date(2026, 7, 13), units="4", on_hand=None),  # sales-only upload
        _week(date(2026, 7, 20), units="6", on_hand="20"),
        _week(date(2026, 7, 27), units="5", on_hand="15"),
    ]
    out = compute_positions(periods, [])
    assert [p.status for p in out] == ["first_report", "no_on_hand", "compared", "compared"]
    gap_week = out[1]
    assert (gap_week.period.start, gap_week.period.end) == (date(2026, 7, 13), date(2026, 7, 19))
    assert gap_week.period.units_sold == D("4") and gap_week.period.on_hand is None
    assert gap_week.gap is None and gap_week.expected is None  # the week itself is not compared
    bridged = out[2]
    assert bridged.previous_on_hand == D("30") and bridged.previous_end == date(2026, 7, 12)
    assert bridged.units_sold_since == D("10")  # 4 in the missing week + 6 in the report week
    assert bridged.expected == D("20") and bridged.gap == D("0")
    assert out[3].previous_on_hand == D("20")
    assert out[3].expected == D("15") and out[3].gap == D("0")


def test_bridge_adds_matched_deliveries_across_the_missing_weeks_and_shows_a_real_gap() -> None:
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="30"),
        _week(date(2026, 7, 13), units="3", on_hand=None),
        _week(date(2026, 7, 20), units="2", on_hand=None),
        _week(date(2026, 7, 27), units="5", on_hand="40"),
    ]
    receipts = [
        Receipt(product_id=1, pod_date=date(2026, 7, 16), units=D("20")),  # inside a missing week
        Receipt(product_id=1, pod_date=date(2026, 7, 10), units=D("9")),  # before the previous report ended
    ]
    out = compute_positions(periods, receipts)
    assert [p.status for p in out] == ["first_report", "no_on_hand", "no_on_hand", "compared"]
    last = out[3]
    assert last.receipts == D("20") and last.units_sold_since == D("10")
    assert last.expected == D("40")  # 30 + 20 - (3 + 2 + 5)
    assert last.gap == D("0")
    short = compute_positions(periods[:3] + [_week(date(2026, 7, 27), units="5", on_hand="35")], receipts)
    assert short[-1].gap == D("-5")


def test_missing_weeks_with_no_sales_either_are_unreported_weeks_and_not_compared() -> None:
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="10"),
        _week(date(2026, 8, 3), units="0", on_hand="10"),
    ]
    out = compute_positions(periods, [])
    # Neither on-hand nor sales for the three weeks between: no row of their own, the next report
    # starts a fresh chain and is named as a data gap.
    assert [p.status for p in out] == ["first_report", "chain_restart"]
    restart = out[1]
    assert restart.gap is None and restart.expected is None
    assert restart.previous_end == date(2026, 7, 12)
    assert restart.notes == ["no sales or on-hand reported for 3 week(s) from 2026-07-13"]


def test_one_unreported_week_among_sales_weeks_starts_a_fresh_chain() -> None:
    """Sales for part of the window only: the sum of sales is incomplete, so nothing is compared."""
    periods = [
        _week(date(2026, 7, 6), units="0", on_hand="30"),
        _week(date(2026, 7, 13), units="4", on_hand=None),
        # 2026-07-20 week: nothing reported
        _week(date(2026, 7, 27), units="6", on_hand="20"),
    ]
    out = compute_positions(periods, [])
    assert [p.status for p in out] == ["first_report", "no_on_hand", "chain_restart"]
    assert out[1].period.start == date(2026, 7, 13) and out[1].period.units_sold == D("4")
    assert out[2].notes == ["no sales or on-hand reported for 1 week(s) from 2026-07-20"]


def test_month_sales_cover_the_weeks_they_span_and_stock_only_rows_do_not() -> None:
    month_sales = ReportPeriod(product_id=1, grain="month", start=date(2026, 7, 1), end=date(2026, 7, 31), units_sold=D("8"))
    stock_only_week = ReportPeriod(
        product_id=1, grain="week", start=date(2026, 7, 13), end=date(2026, 7, 19), units_sold=D("0"), sales_reported=False
    )
    first = _week(date(2026, 6, 29), units="0", on_hand="20")  # ends 2026-07-05
    last = _week(date(2026, 7, 27), units="0", on_hand="12")
    out = compute_positions([first, month_sales, last], [])
    # The July month row covers every missing week of July, so the chain bridges.
    assert out[-1].status == "compared"
    assert out[-1].expected == D("12") and out[-1].gap == D("0")
    # A row that carries no units at all does not count as sales for its week.
    only_stock_row = compute_positions([first, stock_only_week, _week(date(2026, 7, 20), units="0", on_hand="12")], [])
    assert only_stock_row[-1].status == "chain_restart"


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
