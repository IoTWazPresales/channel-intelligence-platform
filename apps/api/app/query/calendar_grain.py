"""Calendar period_grain for P3 volume metrics (week / month / quarter).

Lowest grain is week. Daily is refused. A1 lineup-quarter ``period`` is a different
concept — this module is only for metrics with ``calendar_period: true``.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, cast, func
from sqlalchemy.sql import ColumnElement

PERIOD_GRAINS = frozenset({"week", "month", "quarter"})
DEFAULT_PERIOD_GRAIN = "quarter"

_DAILY_ALIASES = frozenset({"day", "daily", "date", "transaction_date"})
_ALIASES = {
    "weekly": "week",
    "w": "week",
    "iso_week": "week",
    "monthly": "month",
    "m": "month",
    "quarterly": "quarter",
    "q": "quarter",
}

_Q_LABEL = re.compile(r"^(?:20)?(\d{2})[Qq]([1-4])$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

_STORED_RANK = {
    "day": 0,
    "daily": 0,
    "week": 1,
    "weekly": 1,
    "month": 2,
    "monthly": 2,
    "mtd": 2,
    "quarter": 3,
    "quarterly": 3,
    "year": 4,
    "yearly": 4,
    "annual": 4,
}

_REQUEST_RANK = {"week": 1, "month": 2, "quarter": 3}


def normalize_period_grain(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", "_")
    if not s:
        return None
    return _ALIASES.get(s, s)


def is_daily_grain(normalized: str | None) -> bool:
    return bool(normalized) and normalized in _DAILY_ALIASES


def effective_period_grain(raw: Any, *, period_in_grains: bool) -> str | None:
    """Default quarter when the grain set includes ``period``; otherwise None."""
    n = normalize_period_grain(raw)
    if n is not None:
        return n
    if period_in_grains:
        return DEFAULT_PERIOD_GRAIN
    return None


def stored_period_rank(period_type: str | None) -> int:
    p = (period_type or "weekly").strip().lower()
    if p in _STORED_RANK:
        return _STORED_RANK[p]
    for prefix, rank in (("day", 0), ("week", 1), ("month", 2), ("quarter", 3), ("year", 4)):
        if p.startswith(prefix):
            return rank
    return 1  # parsers default weekly


def request_rank(period_grain: str) -> int:
    return _REQUEST_RANK[period_grain]


def finer_than_stored_message(period_grain: str, stored_types: list[str]) -> str:
    shown = ", ".join(sorted({(t or "weekly").strip().lower() or "weekly" for t in stored_types})) or "unknown"
    return (
        f"Requested period_grain={period_grain!r} is finer than stored CST period_type "
        f"({shown}). Never fabricate a finer calendar grain."
    )


def coarsest_stored_rank(period_types: list[str]) -> int:
    if not period_types:
        return 1
    return max(stored_period_rank(t) for t in period_types)


def parse_period_bound(raw: Any, *, end: bool = False) -> date | None:
    """ISO date or PvE-style ``26Q2`` → calendar-quarter bound (not lineup quarter)."""
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    m = _ISO_DATE.match(s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    q = _Q_LABEL.match(s)
    if q:
        year = 2000 + int(q.group(1))
        quarter = int(q.group(2))
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        if not end:
            return start
        end_month = start_month + 2
        last = calendar.monthrange(year, end_month)[1]
        return date(year, end_month, last)
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def bucket_start_to_key(bucket_start: date, period_grain: str) -> str:
    if period_grain == "week":
        iso = bucket_start.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    if period_grain == "month":
        return f"{bucket_start.year:04d}-{bucket_start.month:02d}"
    q = (bucket_start.month - 1) // 3 + 1
    return f"{bucket_start.year:04d}-Q{q}"


def bucket_end(bucket_start: date, period_grain: str) -> date:
    if period_grain == "week":
        return bucket_start + timedelta(days=6)
    if period_grain == "month":
        last = calendar.monthrange(bucket_start.year, bucket_start.month)[1]
        return date(bucket_start.year, bucket_start.month, last)
    q_start_month = ((bucket_start.month - 1) // 3) * 3 + 1
    end_month = q_start_month + 2
    last = calendar.monthrange(bucket_start.year, end_month)[1]
    return date(bucket_start.year, end_month, last)


def as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def date_trunc_expr(date_col: ColumnElement[Any], period_grain: str) -> ColumnElement[Any]:
    if period_grain not in PERIOD_GRAINS:
        raise ValueError(f"Illegal period_grain for date_trunc: {period_grain!r}")
    return cast(func.date_trunc(period_grain, date_col), Date)


def series_point(bucket_start: date, period_grain: str, value: float) -> dict[str, Any]:
    return {
        "bucket_key": bucket_start_to_key(bucket_start, period_grain),
        "bucket_start": bucket_start.isoformat(),
        "bucket_end": bucket_end(bucket_start, period_grain).isoformat(),
        "value": value,
    }
