"""Infer reporting period start and product line for a commercial lineup case.

Pure, deterministic helpers (no DB/I-O):

- ``infer_period_start`` cross-references the user-supplied ``period_label`` (e.g. ``26Q1``,
  ``2026 Q1``, ``FY2026``) with month columns detected in the workbook header
  (Jan/Feb/Mar -> Q1, ...) to produce the first day of the inferred quarter/month.
  The label supplies the year; the columns (or the label's own quarter token) supply the
  quarter. When they disagree a ``period_quarter_mismatch`` flag is raised and the label wins.
- ``infer_product_line`` picks the majority non-empty value from a product-line-style column.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

_MONTH_TO_NUM: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_PRODUCT_LINE_COLUMN_TOKENS: frozenset[str] = frozenset(
    {"productline", "product_line", "line", "category", "bu", "businessunit", "range", "family", "productfamily"}
)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[\s\-_]+", "", str(value).strip().lower())


def _quarter_start_month(quarter: int) -> int:
    return 3 * (quarter - 1) + 1


def detect_months_from_columns(columns: list[str]) -> set[int]:
    """Return the set of month numbers (1-12) that appear as standalone column tokens.

    A header cell counts if any whitespace/punctuation-delimited token within it is a month
    name/abbreviation (so ``Q1 Jan`` and ``Jan-26`` both register January).
    """
    found: set[int] = set()
    for col in columns:
        if col is None:
            continue
        for tok in re.split(r"[\s\-_/]+", str(col).strip().lower()):
            num = _MONTH_TO_NUM.get(tok)
            if num:
                found.add(num)
    return found


def detect_quarter_from_columns(columns: list[str]) -> int | None:
    """Infer a single quarter from detected month columns; None if absent or spanning quarters."""
    months = detect_months_from_columns(columns)
    if not months:
        return None
    quarters = {(m - 1) // 3 + 1 for m in months}
    if len(quarters) == 1:
        return next(iter(quarters))
    return None  # months span multiple quarters -> ambiguous


def _parse_label(period_label: str | None) -> tuple[int | None, int | None, int | None]:
    """Parse a period label into (year, quarter, month). Any element may be None.

    Handles: ``26Q1``, ``2026Q1``, ``Q1 2026``, ``2026-Q2``, ``FY2026``, ``2026``,
    ``Jan 2026``, ``2026-01``.
    """
    if not period_label:
        return None, None, None
    s = str(period_label).strip().lower()

    year: int | None = None
    m4 = re.search(r"(20\d{2})", s)
    if m4:
        year = int(m4.group(1))
    else:
        # Two-digit year adjacent to a quarter token, e.g. "26q1" -> 2026.
        m2 = re.search(r"\b(\d{2})\s*q[1-4]\b", s) or re.search(r"\bq[1-4]\s*(\d{2})\b", s)
        if m2:
            year = 2000 + int(m2.group(1))

    quarter: int | None = None
    mq = re.search(r"q\s*([1-4])", s)
    if mq:
        quarter = int(mq.group(1))

    month: int | None = None
    for tok in re.split(r"[\s\-_/]+", s):
        if tok in _MONTH_TO_NUM:
            month = _MONTH_TO_NUM[tok]
            break
    if month is None:
        mm = re.search(r"20\d{2}[-/](\d{1,2})", s)
        if mm and 1 <= int(mm.group(1)) <= 12:
            month = int(mm.group(1))

    return year, quarter, month


def infer_period_start(period_label: str | None, columns: list[str]) -> tuple[date | None, list[str]]:
    """Return (inferred_period_start, flags).

    Year comes from the label. Quarter/month comes from the label when present, else from
    the workbook's month columns. If both label and columns specify a quarter and they differ,
    flag ``period_quarter_mismatch`` and trust the label.
    """
    flags: list[str] = []
    year, label_quarter, label_month = _parse_label(period_label)
    col_quarter = detect_quarter_from_columns(columns)

    if year is None:
        flags.append("period_year_unknown")
        return None, flags

    if label_month is not None:
        return date(year, label_month, 1), flags

    quarter = label_quarter
    if quarter is not None and col_quarter is not None and quarter != col_quarter:
        flags.append("period_quarter_mismatch")
    elif quarter is None:
        quarter = col_quarter

    if quarter is None:
        # Year known but no quarter/month signal anywhere -> default to start of year, flag it.
        flags.append("period_quarter_unknown")
        return date(year, 1, 1), flags

    return date(year, _quarter_start_month(quarter), 1), flags


def infer_product_line(columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    """Pick the majority non-empty value from a product-line-style column, if one exists.

    ``rows`` are the workbook rows as header-keyed dicts (the parser's ``uploaded`` payload).
    """
    target_col: str | None = None
    for col in columns:
        if _norm(col) in _PRODUCT_LINE_COLUMN_TOKENS:
            target_col = col
            break
    if target_col is None:
        return None

    counts: dict[str, int] = {}
    for row in rows:
        val = row.get(target_col)
        if val is None:
            continue
        text = str(val).strip()
        if text and text.lower() not in ("nan", "none"):
            counts[text] = counts.get(text, 0) + 1
    if not counts:
        return None
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    return best[:64]


def infer_product_line_from_catalogue_values(
    product_lines: list[str | None],
    business_units: list[str | None],
) -> str | None:
    """Majority vote on resolved dim_product.product_line / business_unit when the upload has no line column."""
    counts: dict[str, int] = {}
    for val in (*product_lines, *business_units):
        if val is None:
            continue
        text = str(val).strip()
        if text and text.lower() not in ("nan", "none"):
            key = text[:64]
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]
