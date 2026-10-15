"""N-0111 history upload rules for customer sell-through (Warren 2026-10-16), no database.

- Monday-Sunday is the tenant default week calendar; a customer's own calendar still wins.
- A line with a full sale date stays a day.
- Week (or month) numbers without a year take the year the uploader confirmed; without one,
  every year the parser had to fill in is logged so the load is held. A year is never guessed.
- A stock-only file (on-hand, no units column) parses; its rows carry no units.
"""

from __future__ import annotations

from datetime import date

from app.services.imports.parsers.customer_sell_through_flat import EXPECTED_COLUMNS_META_KEY, parse_flat_report
from app.services.imports.parsers.customer_sell_through_grain import (
    confirmed_year,
    fields_from_token,
    received_on_date,
    suggest_year_from_names,
    week_calendar_from_feed_profile,
    week_fields,
    with_tenant_week_calendar,
    year_guess_log,
)
from app.services.imports.parsers.customer_sell_through_period import classify_period_header

EXPECTED = {
    "units_sold": {"aliases": ["units", "qty"], "required": True},
    "raw_product_token": {"aliases": ["sku"], "required": True},
    "raw_period_ref": {"aliases": ["week", "date"], "required": False},
    "reported_soh": {"aliases": ["soh", "on_hand"], "required": False},
}


def test_tenant_default_is_monday_sunday_and_a_customer_calendar_wins(monkeypatch) -> None:
    import app.services.commercial_tenant_profile as profile

    monkeypatch.setattr(profile, "load_tenant_profile_overrides", lambda _t="default": {})
    assert profile.week_calendar("default") == "monday_sunday"
    filled = with_tenant_week_calendar(None, "default")
    assert week_calendar_from_feed_profile(filled) == {"kind": "iso"}
    assert week_fields(2025, 12, week_calendar=week_calendar_from_feed_profile(filled))["week_start_date"] == date(
        2025, 3, 17
    )
    fiscal = with_tenant_week_calendar({"week_calendar": "fiscal", "fiscal_year_start_month": 3}, "default")
    assert week_calendar_from_feed_profile(fiscal)["kind"] == "fiscal"
    assert week_calendar_from_feed_profile(with_tenant_week_calendar({"week_calendar": "none"}, "default")) is None

    monkeypatch.setattr(profile, "load_tenant_profile_overrides", lambda _t="default": {"week_calendar": "none"})
    assert week_calendar_from_feed_profile(with_tenant_week_calendar(None, "default")) is None


def test_a_full_sale_date_stays_a_day() -> None:
    fields = fields_from_token(date(2025, 3, 12))
    assert fields["period_grain"] == "day" and fields["period_start_date"] == date(2025, 3, 12)


def test_confirmed_year_is_used_and_nothing_is_logged_as_a_guess() -> None:
    with received_on_date(date(2026, 10, 16)), confirmed_year(2024), year_guess_log() as guessed:
        assert classify_period_header("W40")[1] == date(2024, 9, 30)
        assert fields_from_token("Week 12")["period_year"] == 2024
        assert fields_from_token("Sep")["period_start_date"] == date(2024, 9, 1)
    assert guessed == []


def test_without_a_confirmed_year_every_filled_year_is_logged() -> None:
    with received_on_date(date(2026, 10, 16)), year_guess_log() as guessed:
        fields_from_token("Week 12")
        fields_from_token("Sep")
        classify_period_header("FW7")
    assert guessed == ["week 12", "month 9", "fiscal week 7"]


def test_a_stated_year_is_not_a_guess() -> None:
    with year_guess_log() as guessed:
        assert fields_from_token("2024-W12")["period_year"] == 2024
        assert fields_from_token("12/2023")["period_year"] == 2023
    assert guessed == []


def test_year_suggested_from_the_file_name_or_folder() -> None:
    assert suggest_year_from_names("Amazon W12.xlsx", "History/2024") == 2024
    assert suggest_year_from_names("Amazon 2024 week 12.xlsx") == 2024
    assert suggest_year_from_names("sales_20240318.xlsx") is None  # a full date, not a year
    assert suggest_year_from_names("2023 and 2024.xlsx") is None
    assert suggest_year_from_names("weekly.xlsx") is None


def test_week_number_file_logs_a_guess_until_the_year_is_confirmed() -> None:
    data = b"SKU,Week,Units,SOH\nA1,W12,3,10\nA2,W12,1,4\n"
    mapping = {"SKU": "raw_product_token", "Week": "raw_period_ref", "Units": "units_sold", "SOH": "reported_soh",
               EXPECTED_COLUMNS_META_KEY: EXPECTED}
    with received_on_date(date(2026, 10, 16)), year_guess_log() as guessed:
        parse_flat_report(data, "amazon.csv", mapping, 1)
    assert guessed
    with confirmed_year(2024), year_guess_log() as guessed:
        result = parse_flat_report(data, "amazon.csv", mapping, 1)
    assert guessed == []
    assert {r["period_year"] for r in result.rows} == {2024}
    assert {r["period_week"] for r in result.rows} == {12}


def test_stock_only_file_parses_with_no_units() -> None:
    data = b"SKU,Date,SOH\nA1,2025-03-16,10\nA2,2025-03-16,\nA3,2025-03-16,7\n"
    mapping = {"SKU": "raw_product_token", "Date": "raw_period_ref", "SOH": "reported_soh",
               EXPECTED_COLUMNS_META_KEY: EXPECTED}
    result = parse_flat_report(data, "stock.csv", mapping, 1)
    assert result.error is None
    assert [(r["raw_product_token"], r["units_sold"], r["reported_soh"]) for r in result.rows] == [
        ("A1", None, 10.0),
        ("A3", None, 7.0),
    ]
