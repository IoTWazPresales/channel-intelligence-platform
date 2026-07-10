"""Detect month phasing columns in lineup ``raw_row_payload.uploaded`` headers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.commercial_planner.lineup_fiscal_calendar import FiscalCalendarConfig

_MONTH_TO_NUM: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# Absolute cap for plausible lineup unit counts (revenue-scale values fail earlier).
_DEFAULT_MAX_PLAUSIBLE_UNITS = 9_999
_QTY_DISAGREEMENT_RATIO_CAP = 25


def _norm_header(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s*\(tbc\)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_calendar_month_from_column(header: str) -> int | None:
    """Resolve a workbook header to calendar month 1-12 (full, abbrev, dated, TBC-suffixed)."""
    clean = _norm_header(header)
    if not clean:
        return None

    lower = clean.lower()
    for tok in re.split(r"[\s\-_/]+", lower):
        if tok in _MONTH_TO_NUM:
            return _MONTH_TO_NUM[tok]
        m_suffix = re.match(r"^([a-z]{3,9})\d+$", tok)
        if m_suffix and m_suffix.group(1) in _MONTH_TO_NUM:
            return _MONTH_TO_NUM[m_suffix.group(1)]

    m_iso = re.match(r"^(20\d{2})[-/](\d{1,2})$", lower)
    if m_iso:
        mm = int(m_iso.group(2))
        if 1 <= mm <= 12:
            return mm

    m_dated = re.match(r"^([a-z]{3,9})[-\s]?(20\d{2}|\d{2})$", lower)
    if m_dated:
        tok = m_dated.group(1)
        if tok in _MONTH_TO_NUM:
            return _MONTH_TO_NUM[tok]

    return None


def _parse_unit_value(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text or text.lower() in ("tbc", "nan", "none", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_plausible_unit_quantity(
    value: float,
    *,
    qty_cell_hint: float | None = None,
    max_units: int = _DEFAULT_MAX_PLAUSIBLE_UNITS,
) -> bool:
    """Whole-number quantity guard — rejects revenue-scale / non-integer values."""
    if value < 0:
        return False
    if abs(value - round(value)) > 1e-6:
        return False
    if value > max_units:
        return False
    if qty_cell_hint is not None and qty_cell_hint > 0 and value > qty_cell_hint * _QTY_DISAGREEMENT_RATIO_CAP:
        return False
    return True


@dataclass
class MonthColumnDetection:
    """First-instance month column mapping for one lineup row."""

    month_to_column: dict[int, str] = field(default_factory=dict)
    month_values: dict[int, float] = field(default_factory=dict)
    skipped_columns: list[str] = field(default_factory=list)

    @property
    def has_qualifying_block(self) -> bool:
        return bool(self.month_values)

    def months_in_first_half(self, config: FiscalCalendarConfig) -> set[int]:
        from app.services.commercial_planner.lineup_fiscal_calendar import calendar_months_in_first_half

        h1 = calendar_months_in_first_half(config)
        return {m for m in self.month_values if m in h1}


def detect_month_columns(
    uploaded: dict[str, Any] | None,
    *,
    column_order: list[str] | None = None,
    qty_cell_hint: float | None = None,
) -> MonthColumnDetection:
    """Detect month columns using first-instance rule and whole-number guard."""
    out = MonthColumnDetection()
    if not uploaded or not isinstance(uploaded, dict):
        return out

    keys = column_order if column_order else list(uploaded.keys())
    seen_months: set[int] = set()

    for col in keys:
        if col not in uploaded:
            continue
        month = parse_calendar_month_from_column(col)
        if month is None:
            continue
        if month in seen_months:
            out.skipped_columns.append(str(col))
            continue
        seen_months.add(month)
        parsed = _parse_unit_value(uploaded.get(col))
        if parsed is None:
            continue
        if not is_plausible_unit_quantity(parsed, qty_cell_hint=qty_cell_hint):
            out.skipped_columns.append(str(col))
            seen_months.discard(month)
            continue
        out.month_to_column[month] = str(col)
        out.month_values[month] = float(parsed)

    return out
