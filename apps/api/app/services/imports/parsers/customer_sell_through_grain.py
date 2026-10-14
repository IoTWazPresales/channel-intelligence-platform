"""Period grain for customer sell-through rows (N-0110).

A row is stored at the grain the file states:

- a sale date -> ``day`` (the date itself, never moved to a Monday);
- a week number and year -> ``week``; ``week_start_date`` only when the customer's
  week calendar is known (an ISO ``YYYY-Www`` label, a date the file gives as the week
  start, or ``week_calendar`` in the customer's feed profile);
- a month -> ``month``.

``period_start_date`` stays the sort and source-key date: the day, the known week
start, the month start, or for a week with no known calendar the ISO Monday of that
number and year (a bucket key, not a claimed day; ``week_start_date`` stays empty).
"""

from __future__ import annotations

import calendar as _calendar
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from typing import Any, Iterator

import pandas as pd

_ISO_WEEK = re.compile(r"^(\d{4})-?W(\d{1,2})$", re.IGNORECASE)
_WEEK_THEN_YEAR = re.compile(r"^(?:W|WK|WEEK)?\s*[-_ ]?(\d{1,3})\s*[-/. ]\s*(\d{4})$", re.IGNORECASE)
_YEAR_THEN_WEEK = re.compile(r"^(\d{4})\s*[-/ ]\s*(?:W|WK|WEEK)\s*(\d{1,2})$", re.IGNORECASE)
_WEEK_ONLY = re.compile(r"^(?:W|WK|WEEK|FW)\s*[-_ ]?(\d{1,2})$", re.IGNORECASE)
_MONTH = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s/]?(\d{2,4})?$",
    re.IGNORECASE,
)
_MONTH_MAP = {m.lower(): i for i, m in enumerate(_calendar.month_abbr) if m}
_WEEK_HEADER = re.compile(r"\b(week|wk)\b|week[_ ]?(start|commencing|beginning|ending)|w/c", re.IGNORECASE)
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d", "%d-%m-%Y", "%d.%m.%Y")

GRAINS = ("day", "week", "month")


def week_calendar_from_feed_profile(feed_profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """The customer's declared week calendar, or None when it is not known.

    ``{"week_calendar": "iso"}`` or ``{"week_calendar": "fiscal", "fiscal_year_start_month": 3}``.
    """
    if not isinstance(feed_profile, dict):
        return None
    raw = str(feed_profile.get("week_calendar") or "").strip().lower()
    if raw == "iso":
        return {"kind": "iso"}
    if raw == "fiscal":
        try:
            month = int(feed_profile.get("fiscal_year_start_month") or 0)
        except (TypeError, ValueError):
            return None
        if 1 <= month <= 12:
            return {"kind": "fiscal", "fiscal_year_start_month": month}
    return None


def _iso_monday(year: int, week: int) -> date | None:
    try:
        return date.fromisocalendar(int(year), int(week), 1)
    except ValueError:
        return None


# The day the file being parsed was received. A week or month with no year resolves to the
# latest one that had started by then, never to one that had not happened yet (N-0110).
_RECEIVED_ON: ContextVar[date | None] = ContextVar("cst_received_on", default=None)


def received_on() -> date:
    return _RECEIVED_ON.get() or date.today()


@contextmanager
def received_on_date(day: date | None) -> Iterator[None]:
    """Parse with ``day`` as the receive date (default: today)."""
    token = _RECEIVED_ON.set(day)
    try:
        yield
    finally:
        _RECEIVED_ON.reset(token)


def year_for_week(week: int, *, ref: date | None = None) -> int:
    """Year of the latest ISO week ``week`` that started on or before the receive date."""
    ref = ref or received_on()
    for year in (ref.year, ref.year - 1, ref.year - 2):
        start = _iso_monday(year, week)
        if start is not None and start <= ref:
            return year
    return ref.year - 1


def year_for_month(month: int, *, ref: date | None = None) -> int:
    """Year of the latest month ``month`` that started on or before the receive date."""
    ref = ref or received_on()
    return ref.year if int(month) <= ref.month else ref.year - 1


def _fiscal_week_start(year: int, week: int, fy_start_month: int) -> date | None:
    try:
        start = date(int(year), int(fy_start_month), 1)
    except ValueError:
        return None
    while start.weekday() != 0:
        start += timedelta(days=1)
    return start + timedelta(weeks=int(week) - 1)


def week_start_for(year: int, week: int, week_calendar: dict[str, Any] | None) -> date | None:
    if not week_calendar:
        return None
    if week_calendar.get("kind") == "iso":
        return _iso_monday(year, week)
    if week_calendar.get("kind") == "fiscal":
        return _fiscal_week_start(year, week, int(week_calendar["fiscal_year_start_month"]))
    return None


def day_fields(d: date) -> dict[str, Any]:
    return {
        "period_grain": "day",
        "period_type": "daily",
        "period_start_date": d,
        "period_week": None,
        "period_year": None,
        "week_start_date": None,
    }


def week_fields(
    year: int,
    week: int,
    *,
    week_calendar: dict[str, Any] | None = None,
    stated_start: date | None = None,
) -> dict[str, Any] | None:
    if not 1 <= int(week) <= 53:
        return None
    start = stated_start or week_start_for(year, week, week_calendar)
    bucket = start or _iso_monday(year, week) or (date(int(year), 1, 1) + timedelta(weeks=int(week) - 1))
    return {
        "period_grain": "week",
        "period_type": "weekly",
        "period_start_date": bucket,
        "period_week": int(week),
        "period_year": int(year),
        "week_start_date": start,
    }


def stated_week_fields(start: date) -> dict[str, Any]:
    """A week the file gives by its start date: the start is known, the numbering is not."""
    return {
        "period_grain": "week",
        "period_type": "weekly",
        "period_start_date": start,
        "period_week": None,
        "period_year": None,
        "week_start_date": start,
    }


def month_fields(year: int, month: int) -> dict[str, Any] | None:
    try:
        start = date(int(year), int(month), 1)
    except ValueError:
        return None
    return {
        "period_grain": "month",
        "period_type": "monthly",
        "period_start_date": start,
        "period_week": None,
        "period_year": None,
        "week_start_date": None,
    }


def _as_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    # Excel / pandas text such as "2026-07-08 00:00:00"
    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", text):
        try:
            return datetime.fromisoformat(text[:19]).date()
        except ValueError:
            return None
    return None


def fields_from_token(
    value: Any,
    *,
    header: str | None = None,
    week_calendar: dict[str, Any] | None = None,
    year_hint: int | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any] | None:
    """Grain fields for one period cell or label, or None when it is not a period."""
    d = _as_date(value)
    if d is not None:
        if header and _WEEK_HEADER.search(str(header)):
            return stated_week_fields(d)
        return day_fields(d)
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    m = _ISO_WEEK.match(text)
    if m:
        year, week = int(m.group(1)), int(m.group(2))
        return week_fields(year, week, stated_start=_iso_monday(year, week))
    m = _YEAR_THEN_WEEK.match(text)
    if m:
        return week_fields(int(m.group(1)), int(m.group(2)), week_calendar=week_calendar)
    m = _WEEK_THEN_YEAR.match(text)
    if m:
        return week_fields(int(m.group(2)), int(m.group(1)), week_calendar=week_calendar)
    m = _WEEK_ONLY.match(text)
    if m:
        year = year_hint or year_for_week(int(m.group(1)))
        if warnings is not None and year_hint is None:
            warnings.append(f"Week {text!r} has no year; {year} was used")
        return week_fields(year, int(m.group(1)), week_calendar=week_calendar)
    m = _MONTH.match(text)
    if m:
        month = _MONTH_MAP.get(m.group(1)[:3].lower())
        year_raw = m.group(2)
        if month:
            year = int(year_raw) if year_raw else (year_hint or year_for_month(month))
            if year < 100:
                year += 2000
            return month_fields(year, month)
    return None


def stamp_period_grain(row: dict[str, Any], week_calendar: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill grain fields on a staging row a parser left without them.

    Reads the period label first (``raw_period_ref``); otherwise the parser's
    ``period_type``. A week known only by its bucket date keeps the ISO number and
    year of that date and no week start unless the customer's calendar is known.
    """
    if row.get("period_grain") in GRAINS:
        return row
    ref = row.get("raw_period_ref")
    fields = fields_from_token(ref, week_calendar=week_calendar) if ref else None
    if fields is None or (fields["period_grain"] == "day" and str(row.get("period_type") or "").startswith("week")):
        fields = None
    start = row.get("period_start_date")
    if fields is None and isinstance(start, date):
        ptype = str(row.get("period_type") or "weekly").strip().lower()
        if ptype.startswith("month"):
            fields = month_fields(start.year, start.month)
        elif ptype.startswith("da"):
            fields = day_fields(start)
        else:
            iso = start.isocalendar()
            fields = week_fields(iso[0], iso[1], week_calendar=week_calendar)
            if fields is not None and fields["week_start_date"] is None:
                fields["period_start_date"] = start
    if fields is None:
        return row
    for key, value in fields.items():
        if key == "period_start_date" and row.get("period_start_date") is not None and fields["period_grain"] == "week":
            # Keep the parser's bucket date unless the calendar gives a real start.
            if fields.get("week_start_date") is None:
                continue
        row[key] = value
    return row


def period_end(period_start: date, grain: str | None) -> date:
    g = (grain or "week").strip().lower()
    if g == "day":
        return period_start
    if g == "month":
        last = _calendar.monthrange(period_start.year, period_start.month)[1]
        return date(period_start.year, period_start.month, last)
    return period_start + timedelta(days=6)
