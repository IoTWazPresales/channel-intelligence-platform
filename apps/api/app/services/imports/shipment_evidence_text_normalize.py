"""Normalize shipment / order evidence cell text for canonical columns.

Source files may preserve Excel formulas as strings (e.g. ``=MID("SO123",2,5)``). We keep the
original cell payload in ``raw_source_row``; canonical fields use extracted business literals where
we can do so **without inventing** values (no evaluation of arbitrary sheet references).
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any


_RE_FIRST_DQ_LITERAL = re.compile(r'"((?:[^"]|"")*)"')


def unwrap_excel_double_quoted_literal(text: str) -> str | None:
    """If ``text`` looks like an Excel formula, return the first double-quoted literal if any.

    Returns ``None`` when no safe literal can be extracted (caller should keep the trimmed cell).
    """
    t = text.strip()
    if not t.startswith("="):
        return None
    m = _RE_FIRST_DQ_LITERAL.search(t)
    if not m:
        return None
    inner = m.group(1).replace('""', '"')
    return inner if inner.strip() else None


def strip_excel_text_leading_apostrophe(text: str) -> str:
    """Excel text-preservation prefix ``'00123`` → ``00123`` (leading apostrophe only)."""
    if len(text) >= 2 and text[0] == "'" and text[1] not in (" ", "\t"):
        return text[1:]
    return text


def normalize_shipment_text_field(raw: str | None) -> str | None:
    """Trim, unwrap common formula-wrapped literals, strip leading text apostrophe; never invent."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    s = strip_excel_text_leading_apostrophe(s)
    lit = unwrap_excel_double_quoted_literal(s)
    if lit is not None:
        s = lit.strip()
    if not s:
        return None
    return s


def normalize_shipment_cell_value(v: Any) -> str | None:
    """Normalize a tabular cell value after pandas/openpyxl ingestion (non-numeric path)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        if v == int(v):
            return str(int(v))
        t = str(v).strip()
        return t or None
    if isinstance(v, int):
        return str(int(v))
    if isinstance(v, (date, datetime)):
        return None
    if isinstance(v, str):
        return normalize_shipment_text_field(v)
    if hasattr(v, "isoformat"):
        return None
    return normalize_shipment_text_field(str(v))
