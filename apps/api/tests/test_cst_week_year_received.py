"""N-0110: a week or month with no year never resolves to one that had not started when the file was received."""

from __future__ import annotations

from datetime import date

from app.services.imports.parsers.customer_sell_through_grain import (
    fields_from_token,
    received_on_date,
    year_for_month,
    year_for_week,
)
from app.services.imports.parsers.customer_sell_through_period import classify_period_header

RECEIVED = date(2026, 8, 11)


def test_week_not_started_by_receive_date_takes_the_previous_year() -> None:
    assert year_for_week(40, ref=RECEIVED) == 2025
    assert year_for_week(33, ref=RECEIVED) == 2026  # 2026-W33 starts 2026-08-10
    assert year_for_week(34, ref=RECEIVED) == 2025
    assert year_for_week(53, ref=RECEIVED) != 2026  # 2026-W53 starts 2026-12-28


def test_month_not_started_by_receive_date_takes_the_previous_year() -> None:
    assert year_for_month(8, ref=RECEIVED) == 2026
    assert year_for_month(9, ref=RECEIVED) == 2025


def test_parsers_use_the_receive_date() -> None:
    with received_on_date(RECEIVED):
        assert classify_period_header("W40")[1] == date(2025, 9, 29)
        assert fields_from_token("Week 40")["period_year"] == 2025
        assert fields_from_token("Sep")["period_start_date"] == date(2025, 9, 1)
