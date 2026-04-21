"""Product Master tabular hygiene: descriptor rows, NaN/NaT literals, safe strings."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_SLUG = re.compile(r"[^a-z0-9]+")


def slug_for_compare(s: str) -> str:
    return _SLUG.sub("_", (s or "").strip().lower()).strip("_")


# Generic human-readable field labels (not vendor SKUs). Substrings are matched lowercase.
_LABEL_NEEDLES: tuple[str, ...] = (
    " code",
    " id",
    " name",
    " date",
    " unit",
    " type",
    " line",
    "number",
    "description",
    " marketing",
    "sales model",
    "product line",
    "business unit",
    " country ",
    "ean ",
    "ean_",
    "upc ",
    "upc_",
    "gtin",
    "item id",
    "part number",
    "launch date",
    "retire",
    "obsolete",
    "lifecycle",
    "ttv",
    "go live",
)


def normalize_scalar_for_pm(val: Any) -> Any:
    """Coerce pandas/Excel nulls and stringified nulls to None; leave other scalars as-is."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, str):
        t = val.strip()
        if not t:
            return None
        low = t.lower()
        if low in ("nan", "nat", "none", "<na>", "null", "#n/a", "n/a"):
            return None
        return val.strip()
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return None
        return val
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def scalar_to_clean_str(val: Any) -> str | None:
    v = normalize_scalar_for_pm(val)
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, (pd.Timestamp,)):
        return None if pd.isna(v) else str(v)
    return str(v).strip() or None


def looks_like_field_label_text(s: str) -> bool:
    """True if string resembles a column heading / legend cell, not product data."""
    t = (s or "").strip()
    if not t or len(t) > 160:
        return False
    low = t.lower()
    # Long numeric commercial keys are not labels
    if re.search(r"\d{6,}", t):
        return False
    if any(n in low for n in _LABEL_NEEDLES):
        return True
    # Title-ish short phrase with no digits (common pasted header row)
    if " " in t and len(t) < 64 and not any(c.isdigit() for c in t):
        if t[0].isalpha() and sum(1 for c in t if c.isalpha()) >= len(t) * 0.45:
            return True
    return False


def _cell_looks_like_schema_token(s: str) -> bool:
    """Internal field-key style (e.g. marketing_name, bu, country_code) — common pasted legend rows."""
    t = s.strip().lower()
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{1,80}", t))


def row_looks_like_descriptor_row(
    row: pd.Series,
    headers: list[str],
    *,
    tech_col: str | None = None,
    name_col: str | None = None,
) -> bool:
    """Heuristic: row mirrors column titles, or identity columns look like legend labels."""
    mirrors = 0
    nonempty = 0
    labelish = 0
    schema_tokens = 0
    for h in headers:
        if h not in row.index:
            continue
        cell = scalar_to_clean_str(row.get(h))
        if cell is None:
            continue
        nonempty += 1
        if slug_for_compare(cell) == slug_for_compare(str(h)):
            mirrors += 1
        if looks_like_field_label_text(cell):
            labelish += 1
        if _cell_looks_like_schema_token(cell):
            schema_tokens += 1

    if nonempty == 0:
        return False

    if mirrors >= max(2, int(0.28 * len(headers))):
        return True
    if mirrors >= 1 and labelish >= max(2, int(0.4 * nonempty)):
        return True
    if schema_tokens >= max(3, int(0.45 * nonempty)):
        return True

    if tech_col and name_col and tech_col in row.index and name_col in row.index:
        tv = scalar_to_clean_str(row.get(tech_col))
        nv = scalar_to_clean_str(row.get(name_col))
        if tv and nv and looks_like_field_label_text(tv) and looks_like_field_label_text(nv):
            return True

    return False


def strip_leading_descriptor_rows(
    df: pd.DataFrame,
    *,
    tech_col: str | None = None,
    name_col: str | None = None,
    max_scan: int = 12,
) -> tuple[pd.DataFrame, list[int]]:
    """Drop consecutive leading rows that look like a second header / legend row.

    Returns (trimmed_df, list of 0-based iloc positions dropped from the original frame).
    """
    if df.empty:
        return df, []
    headers = [str(c) for c in df.columns.tolist()]
    drop_positions: list[int] = []
    pos = 0
    while pos < len(df) and pos < max_scan:
        r = df.iloc[pos]
        if row_looks_like_descriptor_row(r, headers, tech_col=tech_col, name_col=name_col):
            drop_positions.append(pos)
            pos += 1
        else:
            break
    if not drop_positions:
        return df, []
    trimmed = df.iloc[len(drop_positions) :].copy()
    return trimmed, drop_positions
