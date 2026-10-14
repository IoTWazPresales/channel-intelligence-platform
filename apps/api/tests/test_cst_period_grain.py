"""N-0110: sell-through period grain, in transit / on order, and the sales-only rule (no database)."""

from __future__ import annotations

import io
from datetime import date
from types import SimpleNamespace

import pandas as pd

from app.services.imports.customer_sell_through import (
    NO_ON_HAND_MESSAGE,
    _ingest_parse_result,
    _period_fields_for,
    job_is_sales_only,
    rows_carry_on_hand,
)
from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    ParseResult,
    parse_flat_report,
)
from app.services.imports.parsers.customer_sell_through_grain import (
    fields_from_token,
    stamp_period_grain,
    week_calendar_from_feed_profile,
)

EXPECTED = {
    "raw_product_token": {"aliases": ["sku"]},
    "units_sold": {"aliases": ["units"]},
    "reported_soh": {"aliases": ["soh"]},
    "raw_period_ref": {"aliases": ["week"]},
}


def _xlsx(df: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    df.to_excel(bio, index=False)
    return bio.getvalue()


def _parse(df: pd.DataFrame, filename: str = "report.xlsx", feed_profile=None):
    return parse_flat_report(_xlsx(df), filename, {EXPECTED_COLUMNS_META_KEY: EXPECTED}, 1, feed_profile=feed_profile)


def test_sale_date_is_stored_as_that_day() -> None:
    f = fields_from_token(date(2026, 7, 8))  # a Wednesday
    assert f["period_grain"] == "day"
    assert f["period_start_date"] == date(2026, 7, 8)
    assert f["period_type"] == "daily"


def test_week_number_and_year_without_calendar_has_no_week_start() -> None:
    f = fields_from_token("27/2026")
    assert f["period_grain"] == "week"
    assert (f["period_week"], f["period_year"]) == (27, 2026)
    assert f["week_start_date"] is None
    f = fields_from_token("027.2026")
    assert (f["period_week"], f["period_year"], f["week_start_date"]) == (27, 2026, None)


def test_week_start_filled_only_when_calendar_known() -> None:
    iso = week_calendar_from_feed_profile({"week_calendar": "iso"})
    assert fields_from_token("27/2026", week_calendar=iso)["week_start_date"] == date(2026, 6, 29)
    fiscal = week_calendar_from_feed_profile({"week_calendar": "fiscal", "fiscal_year_start_month": 3})
    # FY week 1 starts on the first Monday on or after 2026-03-01 (2026-03-02).
    assert fields_from_token("W1-2026", week_calendar=fiscal)["week_start_date"] == date(2026, 3, 2)
    assert week_calendar_from_feed_profile({}) is None
    assert week_calendar_from_feed_profile({"week_calendar": "fiscal"}) is None
    # An ISO label states its own calendar.
    assert fields_from_token("2026-W27")["week_start_date"] == date(2026, 6, 29)


def test_month_stays_a_month() -> None:
    f = fields_from_token("Jul 2026")
    assert f["period_grain"] == "month"
    assert f["period_start_date"] == date(2026, 7, 1)
    assert f["period_type"] == "monthly"


def test_week_without_year_warns() -> None:
    warnings: list[str] = []
    f = fields_from_token("W27", warnings=warnings)
    assert f["period_grain"] == "week" and f["period_week"] == 27
    assert warnings and "has no year" in warnings[0]


def test_week_header_date_is_a_stated_week_start_not_a_day() -> None:
    f = fields_from_token(date(2026, 7, 5), header="Week commencing")
    assert f["period_grain"] == "week"
    assert f["week_start_date"] == date(2026, 7, 5)


def test_flat_file_with_sale_dates_keeps_each_day() -> None:
    df = pd.DataFrame(
        {
            "SKU": ["A1", "A1"],
            "Units": [2, 3],
            "SOH": [10, 7],
            "Sale Date": [pd.Timestamp("2026-07-07"), pd.Timestamp("2026-07-08")],
        }
    )
    result = _parse(df)
    assert result.error is None
    assert [r["period_grain"] for r in result.rows] == ["day", "day"]
    assert [r["period_start_date"] for r in result.rows] == [date(2026, 7, 7), date(2026, 7, 8)]
    assert {r["period_type"] for r in result.rows} == {"daily"}


def test_flat_file_week_column_keeps_number_and_year() -> None:
    df = pd.DataFrame({"SKU": ["A1"], "Units": [2], "SOH": [10], "Week": ["27/2026"]})
    row = _parse(df).rows[0]
    assert (row["period_grain"], row["period_week"], row["period_year"]) == ("week", 27, 2026)
    assert row["week_start_date"] is None


def test_flat_file_in_transit_and_on_order_stored_apart() -> None:
    df = pd.DataFrame(
        {"SKU": ["A1"], "Units": [2], "SOH": [10], "In Transit": [4], "On Order": [12], "Week": ["27/2026"]}
    )
    row = _parse(df).rows[0]
    assert row["reported_soh"] == 10
    assert row["in_transit_units"] == 4
    assert row["on_order_units"] == 12


def test_file_name_range_of_one_day_is_a_day() -> None:
    df = pd.DataFrame({"SKU": ["A1"], "Units": [2], "SOH": [10]})
    row = _parse(df, filename="sales_20260708_20260708.xlsx").rows[0]
    assert row["period_grain"] == "day"
    assert row["period_start_date"] == date(2026, 7, 8)


def test_file_name_whole_month_is_a_month() -> None:
    df = pd.DataFrame({"SKU": ["A1"], "Units": [2], "SOH": [10]})
    row = _parse(df, filename="sales_20260701_20260731.xlsx").rows[0]
    assert row["period_grain"] == "month"
    assert row["period_start_date"] == date(2026, 7, 1)


def test_rows_without_on_hand_are_detected() -> None:
    df = pd.DataFrame({"SKU": ["A1"], "Units": [2], "Week": ["27/2026"]})
    result = _parse(df)
    assert result.error is None
    assert rows_carry_on_hand(result.rows) is False
    assert rows_carry_on_hand([{"reported_soh": 0}]) is True


def _job(meta: dict) -> SimpleNamespace:
    return SimpleNamespace(id=1, staged_metadata=meta, stage=None, status=None, error_summary=None)


def test_units_without_on_hand_are_refused_unless_sales_only() -> None:
    result = ParseResult(rows=[{"units_sold": 2.0, "reported_soh": None}])
    job = _job({})
    assert _ingest_parse_result(None, job, customer_id=1, result=result, structure_type="pivoted", summary_key="k") == 1
    assert job.error_summary and "no on-hand column" in job.error_summary
    assert NO_ON_HAND_MESSAGE.startswith("This file has units sold and no on-hand column")
    assert job_is_sales_only(_job({"cst_sales_only": True})) is True
    assert job_is_sales_only(_job({})) is False


def test_stamp_leaves_parser_bucket_when_calendar_unknown() -> None:
    row = {"period_start_date": date(2026, 6, 29), "period_type": "weekly", "raw_period_ref": "Sales U TY"}
    stamp_period_grain(row)
    assert row["period_grain"] == "week"
    assert (row["period_week"], row["period_year"]) == (27, 2026)
    assert row["week_start_date"] is None
    assert row["period_start_date"] == date(2026, 6, 29)


def test_stamp_month_and_label() -> None:
    row = {"period_start_date": date(2026, 7, 1), "period_type": "monthly", "raw_period_ref": None}
    assert stamp_period_grain(row)["period_grain"] == "month"
    row = {"period_start_date": date(2026, 6, 29), "period_type": "weekly", "raw_period_ref": "2026-W27"}
    stamp_period_grain(row)
    assert row["week_start_date"] == date(2026, 6, 29)


def test_steward_declared_period_keeps_the_grain() -> None:
    assert _period_fields_for("day", date(2026, 7, 9), None)["period_start_date"] == date(2026, 7, 9)
    wk = _period_fields_for("week", date(2026, 7, 6), None)
    assert wk["period_grain"] == "week" and wk["period_start_date"] == date(2026, 7, 6)
    assert _period_fields_for("month", date(2026, 7, 1), None)["period_grain"] == "month"
