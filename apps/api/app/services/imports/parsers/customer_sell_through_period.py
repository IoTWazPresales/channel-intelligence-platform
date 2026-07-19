# Plan (Phase 1b-e shared period utilities):
# - Generic period header detection via regex (no retailer-specific column names).
# - Convert headers to period_start_date for pivoted / multi-sheet / wide unpivot paths.
# - Fiscal week: week 1 = first ISO week starting on or after fiscal year start (default Jan 1).

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from app.services.imports.parsers.customer_sell_through_flat import _monday_of_week, _normalize_text, _parse_date_value

_ISO_WEEK_HEADER = re.compile(r"^(\d{4})-?W(\d{1,2})$", re.IGNORECASE)
_WEEK_YEAR_HEADER = re.compile(r"^W(\d{1,2})[-/](\d{4})$", re.IGNORECASE)
_WEEK_ONLY_HEADER = re.compile(r"^W(\d{1,2})$", re.IGNORECASE)
_FW_HEADER = re.compile(r"^FW[-\s]?(\d{1,2})$", re.IGNORECASE)
_NN_YYYY_HEADER = re.compile(r"^(\d{1,2})[-/](\d{4})$")
_DATE_HEADER = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_YEAR_HEADER = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s]?(\d{2,4})?$",
    re.IGNORECASE,
)

_MONTH_MAP = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def fiscal_year_start_month(field_mapping: dict) -> int:
    raw = field_mapping.get("fiscal_year_start_month") or field_mapping.get("__fiscal_year_start_month__")
    if raw is None:
        return 1
    try:
        m = int(raw)
        return m if 1 <= m <= 12 else 1
    except (TypeError, ValueError):
        return 1


def _fiscal_week_monday(year: int, fiscal_week: int, fy_start_month: int) -> date | None:
    """Fiscal week 1 starts on Monday of the first ISO week on/after FY start."""
    try:
        fy_start = date(year, fy_start_month, 1)
    except ValueError:
        return None
    # First Monday on or after FY start
    while fy_start.weekday() != 0:
        fy_start += timedelta(days=1)
    try:
        return fy_start + timedelta(weeks=fiscal_week - 1)
    except OverflowError:
        return None


def classify_period_header(header: str) -> tuple[str, date | None, str]:
    """Return (kind, period_start_date, period_type) or ('unknown', None, 'weekly')."""
    text = _normalize_text(header)
    if not text:
        return "unknown", None, "weekly"
    h = text.strip()

    m = _ISO_WEEK_HEADER.match(h)
    if m:
        try:
            return "iso_week", date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1), "weekly"
        except ValueError:
            return "unknown", None, "weekly"

    m = _WEEK_YEAR_HEADER.match(h)
    if m:
        try:
            return "iso_week", date.fromisocalendar(int(m.group(2)), int(m.group(1)), 1), "weekly"
        except ValueError:
            return "unknown", None, "weekly"

    m = _WEEK_ONLY_HEADER.match(h)
    if m:
        week_no = int(m.group(1))
        year = date.today().year
        try:
            return "iso_week", date.fromisocalendar(year, week_no, 1), "weekly"
        except ValueError:
            return "unknown", None, "weekly"

    m = _FW_HEADER.match(h)
    if m:
        fw = int(m.group(1))
        year = date.today().year
        d = _fiscal_week_monday(year, fw, 1)
        if d:
            return "fiscal_week", d, "weekly"
        return "unknown", None, "weekly"

    m = _NN_YYYY_HEADER.match(h)
    if m:
        week_no = int(m.group(1))
        year = int(m.group(2))
        try:
            return "iso_week", date.fromisocalendar(year, week_no, 1), "weekly"
        except ValueError:
            return "unknown", None, "weekly"

    if _DATE_HEADER.match(h):
        d = _parse_date_value(h)
        if d:
            return "date", d, "weekly"

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(h[:10], fmt).date()
            return "date", _monday_of_week(parsed), "weekly"
        except ValueError:
            continue

    m = _MONTH_YEAR_HEADER.match(h)
    if m:
        mon_name = m.group(1)[:3].lower()
        month = _MONTH_MAP.get(mon_name)
        if month:
            yr_raw = m.group(2)
            if yr_raw:
                yr = int(yr_raw)
                if yr < 100:
                    yr += 2000
            else:
                yr = date.today().year
            try:
                return "month", date(yr, month, 1), "monthly"
            except ValueError:
                pass

    return "unknown", None, "weekly"


def is_period_column_header(header: str) -> bool:
    kind, _, _ = classify_period_header(header)
    return kind != "unknown"


def detect_period_columns(headers: list[str]) -> list[tuple[str, date | None, str]]:
    """Return list of (column_name, period_start_date, period_type) for period columns."""
    out: list[tuple[str, date | None, str]] = []
    for h in headers:
        if not h or str(h).startswith("col_"):
            continue
        kind, pdate, ptype = classify_period_header(str(h))
        if kind != "unknown" and pdate is not None:
            out.append((str(h), pdate, ptype))
    return out


def parse_sheet_name_period(sheet_name: str) -> tuple[date | None, str, str | None]:
    """Return (period_start_date, period_type, warning_or_none)."""
    name = (sheet_name or "").strip()
    if not name:
        return None, "weekly", "Period could not be detected from sheet name: (empty)"

    week_m = re.search(r"(?:week|wk|w)[\s\-]*(\d{1,2})\b", name, re.IGNORECASE)
    if week_m:
        week_no = int(week_m.group(1))
        year = date.today().year
        try:
            return date.fromisocalendar(year, week_no, 1), "weekly", None
        except ValueError:
            pass

    kind, pdate, ptype = classify_period_header(name)
    if pdate is not None:
        return pdate, ptype, None

    d = _parse_date_value(name)
    if d is not None:
        return d, "weekly", None

    return None, "weekly", f"Period could not be detected from sheet name: {sheet_name}"


def is_summary_sheet_name(sheet_name: str) -> bool:
    return bool(re.search(r"\b(summary|index|overview|cover|instructions|readme)\b", sheet_name or "", re.IGNORECASE))


def sheet_has_data_header(raw_df: pd.DataFrame, alias_index: dict[str, set[str]], min_score: int = 2) -> bool:
    from app.services.imports.parsers.customer_sell_through_flat import _detect_header_row, _score_header_row

    if raw_df is None or raw_df.empty:
        return False
    if _detect_header_row(raw_df, alias_index) is not None:
        return True
    limit = min(10, len(raw_df))
    for i in range(limit):
        if _score_header_row(raw_df.iloc[i].tolist(), alias_index) >= min_score:
            return True
    return False


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def sort_period_columns(cols: list[tuple[str, date | None, str]]) -> list[tuple[str, date | None, str]]:
    return sorted(cols, key=lambda x: (x[1] or date.min, x[0]))
