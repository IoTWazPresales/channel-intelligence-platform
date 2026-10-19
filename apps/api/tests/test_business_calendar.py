"""Tenant business calendar (Warren 2026-10-19): days roll up into the tenant's weeks, months,
quarters and years, whatever calendar the company uses."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.business_calendar import BusinessCalendar, normalize_calendar_config


def test_default_is_calendar_year_with_monday_weeks():
    cal = BusinessCalendar()
    q = cal.bucket(date(2026, 10, 19), "quarter")
    assert (q.start, q.end, q.label) == (date(2026, 10, 1), date(2026, 12, 31), "26Q4")
    w = cal.bucket(date(2026, 10, 19), "week")
    assert (w.start, w.end, w.label) == (date(2026, 10, 19), date(2026, 10, 25), "W43")
    assert cal.year(date(2026, 3, 3)).label == "2026"


def test_financial_year_starting_april_named_by_end_year():
    cal = BusinessCalendar({"type": "gregorian", "fiscal_year_start_month": 4})
    yr = cal.year(date(2026, 10, 19))
    assert (yr.start, yr.end, yr.label) == (date(2026, 4, 1), date(2027, 3, 31), "FY27")
    q = cal.bucket(date(2026, 10, 19), "quarter")
    assert (q.start, q.end, q.label, q.quarter) == (date(2026, 10, 1), date(2026, 12, 31), "27Q3", 3)
    q4 = cal.bucket(date(2027, 2, 10), "quarter")
    assert (q4.start, q4.end, q4.label) == (date(2027, 1, 1), date(2027, 3, 31), "27Q4")


def test_financial_year_named_by_start_year():
    cal = BusinessCalendar({"type": "gregorian", "fiscal_year_start_month": 4, "fiscal_year_named_by": "start"})
    assert cal.year(date(2027, 1, 5)).label == "FY26"


def test_retail_445_whole_weeks():
    cal = BusinessCalendar({"type": "retail_445", "fiscal_year_start_month": 1})
    yr = cal.year(date(2026, 6, 1))
    # Year ends on the last Sunday of December; weeks run Monday-Sunday.
    assert yr.end == date(2026, 12, 27)
    assert yr.start == date(2025, 12, 29)
    assert yr.start.weekday() == 0
    months = cal.buckets(yr.start, yr.end, "month")
    assert [m.days // 7 for m in months] == [4, 4, 5] * 4
    quarters = cal.buckets(yr.start, yr.end, "quarter")
    assert all(q.days == 91 for q in quarters)


def test_retail_53rd_week_joins_the_last_period():
    cal = BusinessCalendar({"type": "retail_445", "fiscal_year_start_month": 1})
    years = [cal.year(date(y, 6, 1)) for y in range(2020, 2035)]
    assert {yr.days // 7 for yr in years} == {52, 53}
    yr = next(yr for yr in years if yr.days // 7 == 53)
    months = cal.buckets(yr.start, yr.end, "month")
    assert months[-1].days == 6 * 7


def test_custom_calendar_periods():
    cal = BusinessCalendar(
        {
            "type": "custom",
            "custom_periods": [
                {"start": "2026-01-05", "fiscal_year": 2026, "quarter": 1, "label": "Jan"},
                {"start": "2026-02-02", "fiscal_year": 2026, "quarter": 1},
                {"start": "2026-03-02", "fiscal_year": 2026, "quarter": 1},
                {"start": "2026-04-06", "fiscal_year": 2026, "quarter": 2},
            ],
        }
    )
    m = cal.bucket(date(2026, 1, 20), "month")
    assert (m.start, m.end, m.label) == (date(2026, 1, 5), date(2026, 2, 1), "Jan")
    q = cal.bucket(date(2026, 2, 20), "quarter")
    assert (q.start, q.end, q.label) == (date(2026, 1, 5), date(2026, 4, 5), "26Q1")


def test_buckets_cover_range_without_gaps():
    cal = BusinessCalendar({"type": "retail_454", "fiscal_year_start_month": 2, "week_start_day": 6})
    bs = cal.buckets(date(2026, 1, 1), date(2026, 12, 31), "month")
    for a, b in zip(bs, bs[1:]):
        assert (b.start - a.end).days == 1
    assert all(b.start.weekday() == 6 for b in bs[1:])


def test_same_day_last_year():
    assert BusinessCalendar().same_day_last_year(date(2026, 10, 19)) == date(2025, 10, 19)
    retail = BusinessCalendar({"type": "retail_445"})
    d = date(2026, 10, 19)
    prior = retail.same_day_last_year(d)
    assert prior.weekday() == d.weekday()
    assert retail.bucket(prior, "week").label == retail.bucket(d, "week").label


def test_invalid_setting_is_refused():
    with pytest.raises(ValueError):
        normalize_calendar_config({"type": "lunar"})
    with pytest.raises(ValueError):
        normalize_calendar_config({"type": "custom", "custom_periods": []})
    assert normalize_calendar_config({"type": "lunar"}, strict=False)["type"] == "gregorian"
