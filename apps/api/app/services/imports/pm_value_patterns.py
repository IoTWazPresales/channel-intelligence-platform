"""Strict value-shape checks for Product Master mapping (generic, reusable)."""

from __future__ import annotations

import re
from typing import Literal

_RE_ISO_LIKE = re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}"  # date
    r"|^\d{1,2}[-/]\d{1,2}[-/]\d{4}"
    r"|^\d{4}-\d{2}-\d{2}[T ]\d"  # datetime
    r"|^\d{2}:\d{2}:\d{2}",
    re.I,
)
_RE_LONG_PROSE = re.compile(r"\b(the|and|with|for|from|this|that|your|our|inch|diagonal|features)\b", re.I)


def looks_like_calendar_date_or_datetime(s: str) -> bool:
    t = str(s).strip()
    if not t:
        return False
    if _RE_ISO_LIKE.search(t):
        return True
    if re.match(r"^\d{1,2}[./]\d{1,2}[./]\d{2,4}$", t):
        return True
    return False


def is_strict_barcode_candidate(s: str) -> bool:
    """True only if value is predominantly a GTIN/UPC digit string (benign separators only)."""
    t = str(s).strip()
    if not t:
        return False
    if looks_like_calendar_date_or_datetime(t):
        return False
    # Reject prose / marketing blobs
    if len(t) > 22:
        return False
    if _RE_LONG_PROSE.search(t):
        return False
    letters = sum(1 for c in t if c.isalpha())
    if letters > 0:
        return False
    digits = re.sub(r"\D", "", t)
    if len(digits) not in (8, 11, 12, 13, 14):
        return False
    # Embedded digit islands with letters already rejected
    return True


def best_barcode_kind_from_samples(
    samples: list[str],
) -> tuple[Literal["barcode_ean", "barcode_upc"] | None, list[str]]:
    """Return strongest barcode target from samples that pass strict checks; evidence reason tags."""
    kinds: list[tuple[str, str]] = []
    for raw in samples[:8]:
        s = str(raw).strip()
        if not is_strict_barcode_candidate(s):
            continue
        d = re.sub(r"\D", "", s)
        if len(d) in (13, 14, 8):
            kinds.append(("barcode_ean", d))
        elif len(d) in (12, 11):
            kinds.append(("barcode_upc", d))
    if not kinds:
        return None, []
    # Prefer EAN-13 family when present
    for k, dg in kinds:
        if len(dg) >= 13:
            return "barcode_ean", ["barcode_like_value"]
    for k, dg in kinds:
        if k == "barcode_ean":
            return "barcode_ean", ["barcode_like_value"]
    return "barcode_upc", ["barcode_like_value"]
