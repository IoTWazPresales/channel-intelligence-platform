"""Commercial lineup parse: month_split_json + month-derived 1H quantity (no uniform_half).

Reuses historical shape (header label → float) and ``detect_month_columns`` for
``May\\n(TBC)``-style headers. Does not modify ``historical_lineup.py``.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from app.services.commercial_planner.lineup_fiscal_calendar import (
    calendar_months_in_fiscal_quarter,
    get_lineup_fiscal_calendar_config,
)
from app.services.commercial_planner.lineup_month_column_detector import detect_month_columns
from app.services.commercial_planner.lineup_month_derived_allocation import MONTH_DERIVED_ALLOCATION_FLAG

HALF_YEAR_SPLIT_REQUIRES_MONTH_COLUMNS = "half_year_split_requires_month_columns"
HalfName = Literal["q1", "q2"]

# ACZA workbooks pair unit months (Feb) with revenue companions (Feb2). Historical path
# only accepts exact 3-letter abbrevs; digit-suffix headers must not enter month_split_json.
_MONTH_DIGIT_COMPANION = re.compile(
    r"^(jan|january|feb|february|mar|march|apr|april|may|jun|june|"
    r"jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\d+$",
    re.IGNORECASE,
)


class HalfYearSplitRequiresMonthColumnsError(ValueError):
    """1H parse requested but workbook has no usable month phasing columns."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or HALF_YEAR_SPLIT_REQUIRES_MONTH_COLUMNS)
        self.reason = HALF_YEAR_SPLIT_REQUIRES_MONTH_COLUMNS


def _is_month_digit_companion_header(header: str) -> bool:
    text = str(header).strip().lower()
    text = re.sub(r"\s*\(tbc\)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\s\-_\n]+", "", text)
    return bool(_MONTH_DIGIT_COMPANION.match(text))


def _filter_uploaded_for_month_units(uploaded: dict[str, Any] | None) -> dict[str, Any] | None:
    if not uploaded:
        return uploaded
    return {k: v for k, v in uploaded.items() if not _is_month_digit_companion_header(str(k))}


def _qty_hint_from_row(row: dict[str, Any]) -> float | None:
    q = row.get("quantity_units")
    if q is None:
        return None
    try:
        return float(q)
    except (TypeError, ValueError):
        return None


def workbook_has_month_columns(uploaded_rows: list[dict[str, Any] | None]) -> bool:
    """True when any row's uploaded headers resolve to at least one month column with a value."""
    for uploaded in uploaded_rows:
        filtered = _filter_uploaded_for_month_units(uploaded)
        if not filtered:
            continue
        det = detect_month_columns(filtered, column_order=list(filtered.keys()))
        if det.has_qualifying_block:
            return True
    return False


def build_month_split_json_from_uploaded(
    uploaded: dict[str, Any] | None,
    *,
    qty_cell_hint: float | None = None,
    half: HalfName | None = None,
) -> dict[str, float] | None:
    """Build historical-shaped ``month_split_json``: ``{header_label: float}``.

    When ``half`` is set, only months belonging to that fiscal quarter are included.
    """
    filtered = _filter_uploaded_for_month_units(uploaded)
    if not filtered:
        return None
    detection = detect_month_columns(
        filtered,
        column_order=list(filtered.keys()),
        qty_cell_hint=qty_cell_hint,
    )
    if not detection.has_qualifying_block:
        return None

    months = set(detection.month_values.keys())
    if half is not None:
        config = get_lineup_fiscal_calendar_config()
        fq = 1 if half == "q1" else 2
        months = months & set(calendar_months_in_fiscal_quarter(fq, config))

    out: dict[str, float] = {}
    for m in sorted(months):
        col = detection.month_to_column.get(m)
        if col is None:
            continue
        out[str(col)] = float(detection.month_values[m])
    return out or None


def sum_month_split_units(month_split: dict[str, float] | None) -> float:
    if not month_split:
        return 0.0
    return float(sum(month_split.values()))


def apply_month_derived_half_to_row_dict(
    row: dict[str, Any],
    *,
    half: HalfName,
    file_has_month_columns: bool | None = None,
) -> dict[str, Any]:
    """Derive ``quantity_units`` + half ``month_split_json`` from real monthly cells.

    File-level gate: when the workbook has no month columns at all, raises
    ``HalfYearSplitRequiresMonthColumnsError``. Per-row missing months yield quantity 0.
    Does not call ``allocate_uniform_half``.
    """
    raw = dict(row.get("raw_row_payload") or {})
    uploaded = raw.get("uploaded") if isinstance(raw.get("uploaded"), dict) else None
    filtered = _filter_uploaded_for_month_units(uploaded)
    detection = detect_month_columns(
        filtered,
        column_order=list(filtered.keys()) if filtered else None,
        qty_cell_hint=_qty_hint_from_row(row),
    )
    has_months = (
        file_has_month_columns
        if file_has_month_columns is not None
        else detection.has_qualifying_block
    )
    if not has_months:
        raise HalfYearSplitRequiresMonthColumnsError(
            f"{HALF_YEAR_SPLIT_REQUIRES_MONTH_COLUMNS}: "
            "1H split requires month phasing columns; refusing uniform_half fabrication"
        )

    half_split = build_month_split_json_from_uploaded(
        uploaded,
        qty_cell_hint=_qty_hint_from_row(row),
        half=half,
    )
    full_split = build_month_split_json_from_uploaded(
        uploaded,
        qty_cell_hint=_qty_hint_from_row(row),
        half=None,
    )

    out = dict(row)
    out_raw = dict(raw)
    if full_split:
        out_raw["half_year_source_month_split_json"] = full_split
    source_qty = out.get("quantity_units")
    if source_qty is not None:
        out_raw["half_year_source_quantity_units"] = source_qty

    allocated = sum_month_split_units(half_split)
    out["quantity_units"] = allocated
    if half_split:
        out["month_split_json"] = half_split
    else:
        out.pop("month_split_json", None)
    diag = [c for c in (out.get("diagnostic_codes") or []) if c != "allocation=uniform_half"]
    if MONTH_DERIVED_ALLOCATION_FLAG not in diag:
        diag.append(MONTH_DERIVED_ALLOCATION_FLAG)
    out["diagnostic_codes"] = diag
    out["raw_row_payload"] = out_raw
    return out


def attach_month_split_json_to_row_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Populate ``month_split_json`` on a non-1H (or pre-split) parse row from uploaded months."""
    if row.get("month_split_json"):
        return row
    raw = dict(row.get("raw_row_payload") or {})
    uploaded = raw.get("uploaded") if isinstance(raw.get("uploaded"), dict) else None
    ms = build_month_split_json_from_uploaded(
        uploaded,
        qty_cell_hint=_qty_hint_from_row(row),
        half=None,
    )
    if not ms:
        return row
    out = dict(row)
    out["month_split_json"] = ms
    return out
