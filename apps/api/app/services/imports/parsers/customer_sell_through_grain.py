"""Period grain for customer sell-through rows (N-0110).

A row is stored at the grain the file states:

- a sale date -> ``day`` (the date itself, never moved to a Monday);
- a week number and year -> ``week``; ``week_start_date`` only when the customer's
  week calendar is known (an ISO ``YYYY-Www`` label, a date the file gives as the week
  start, ``week_calendar`` in the customer's feed profile, or the tenant default:
  Monday-Sunday, N-0111);
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
    ``{"week_calendar": "none"}`` turns the tenant default off for one customer.
    Use ``with_tenant_week_calendar`` first so the tenant default applies.
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


def with_tenant_week_calendar(feed_profile: dict[str, Any] | None, tenant_id: str | None) -> dict[str, Any]:
    """The feed profile with the tenant default week calendar filled in when it names none (N-0111).

    Every customer reports Monday-Sunday weeks (Warren 2026-10-16), so the default is ``iso``
    (ISO weeks run Monday to Sunday). A customer's own ``week_calendar`` always wins.
    """
    out = dict(feed_profile) if isinstance(feed_profile, dict) else {}
    if str(out.get("week_calendar") or "").strip():
        return out
    from app.services.commercial_tenant_profile import week_calendar as tenant_week_calendar

    if tenant_week_calendar((tenant_id or "default").strip() or "default") == "monday_sunday":
        out["week_calendar"] = "iso"
    return out


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


# N-0111: a year is never guessed. The uploader confirms the year of a file that carries only
# week (or month) numbers; until then every year the parser had to fill in is logged here and
# the load does not apply (Warren 2026-10-16).
_CONFIRMED_YEAR: ContextVar[int | None] = ContextVar("cst_confirmed_year", default=None)
_YEAR_GUESSES: ContextVar[list[str] | None] = ContextVar("cst_year_guesses", default=None)


@contextmanager
def confirmed_year(year: int | None) -> Iterator[None]:
    """Parse with ``year`` as the uploader-confirmed year for week or month numbers."""
    token = _CONFIRMED_YEAR.set(int(year) if year else None)
    try:
        yield
    finally:
        _CONFIRMED_YEAR.reset(token)


@contextmanager
def year_guess_log() -> Iterator[list[str]]:
    """Collect every label whose year the parser had to fill in without a confirmed year."""
    log: list[str] = []
    token = _YEAR_GUESSES.set(log)
    try:
        yield log
    finally:
        _YEAR_GUESSES.reset(token)


def current_year_guesses() -> list[str]:
    """Labels logged in the innermost ``year_guess_log`` (empty outside one)."""
    return list(_YEAR_GUESSES.get() or [])


def _note_guess(label: str) -> None:
    log = _YEAR_GUESSES.get()
    if log is not None:
        log.append(label)


def year_for_week(week: int, *, ref: date | None = None) -> int:
    """The confirmed year; otherwise the latest ISO week ``week`` started by the receive date.

    The fallback is a placeholder that is logged as a guess: a load with a guessed year
    does not apply (N-0111).
    """
    year = _CONFIRMED_YEAR.get()
    if year:
        return year
    _note_guess(f"week {int(week)}")
    ref = ref or received_on()
    for year in (ref.year, ref.year - 1, ref.year - 2):
        start = _iso_monday(year, week)
        if start is not None and start <= ref:
            return year
    return ref.year - 1


def year_for_month(month: int, *, ref: date | None = None) -> int:
    """The confirmed year; otherwise the latest month ``month`` started by the receive date (logged)."""
    year = _CONFIRMED_YEAR.get()
    if year:
        return year
    _note_guess(f"month {int(month)}")
    ref = ref or received_on()
    return ref.year if int(month) <= ref.month else ref.year - 1


def year_for_fiscal_week(week: int) -> int | None:
    """The confirmed year for a fiscal week number, or None after logging that it is unknown."""
    year = _CONFIRMED_YEAR.get()
    if year:
        return year
    _note_guess(f"fiscal week {int(week)}")
    return None


_YEAR_IN_NAME = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def suggest_year_from_names(*names: str | None) -> int | None:
    """The one year (2000-2099) the file name or its folder states, for the uploader to confirm.

    A name with a full date (``20240318``) is not read as a year; two different years give None.
    """
    years: set[int] = set()
    for name in names:
        for m in _YEAR_IN_NAME.finditer(str(name or "")):
            years.add(int(m.group(1)))
    return years.pop() if len(years) == 1 else None


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
        year = _CONFIRMED_YEAR.get() or year_hint or year_for_week(int(m.group(1)))
        if warnings is not None and year_hint is None and not _CONFIRMED_YEAR.get():
            warnings.append(f"Week {text!r} has no year; {year} was used")
        return week_fields(year, int(m.group(1)), week_calendar=week_calendar)
    m = _MONTH.match(text)
    if m:
        month = _MONTH_MAP.get(m.group(1)[:3].lower())
        year_raw = m.group(2)
        if month:
            year = int(year_raw) if year_raw else (_CONFIRMED_YEAR.get() or year_hint or year_for_month(month))
            if year < 100:
                year += 2000
            return month_fields(year, month)
    return None


def roll_bare_week_years(
    rows: list[dict[str, Any]],
    *,
    year_hint: int | None = None,
    week_calendar: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Roll the year of bare week numbers forward at the year end within one file (N-0111).

    A file can run from week 52 or 53 into week 1 (Warren 2026-10-16: no manual split). Each
    product and site is read in file order from the file's year (confirmed, else the file name's)
    and moves one year on where its week number drops back. A product whose first row is a week
    that every other product placed in one year takes that year, so a product with no sale in
    week 52 still lands its week 1 in the new year. Rows with a stated year are not touched.
    """
    base = _CONFIRMED_YEAR.get() or year_hint
    if not base:
        return rows
    bare: list[tuple[int, tuple[Any, Any], int]] = []
    for i, row in enumerate(rows):
        m = _WEEK_ONLY.match(str(row.get("raw_period_ref") or "").strip())
        if m and row.get("period_grain") == "week":
            bare.append((i, (row.get("raw_product_token"), row.get("raw_location_token")), int(m.group(1))))
    if not bare:
        return rows
    last: dict[tuple[Any, Any], tuple[int, int]] = {}
    offset: dict[int, int] = {}
    first: dict[tuple[Any, Any], int] = {}
    for i, key, week in bare:
        if key in last:
            prev_week, prev_off = last[key]
            offset[i] = prev_off + (1 if week < prev_week else 0)
        else:
            offset[i] = 0
            first[key] = i
        last[key] = (week, offset[i])
    later: dict[int, set[int]] = {}
    firsts = set(first.values())
    for i, _key, week in bare:
        if i not in firsts:
            later.setdefault(week, set()).add(offset[i])
    shift: dict[tuple[Any, Any], int] = {}
    for key, i in first.items():
        week = next(w for j, _k, w in bare if j == i)
        seen = later.get(week) or set()
        if len(seen) == 1:
            shift[key] = next(iter(seen))
    for i, key, week in bare:
        fields = week_fields(int(base) + offset[i] + shift.get(key, 0), week, week_calendar=week_calendar)
        if fields is not None:
            rows[i].update(fields)
    return rows


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
