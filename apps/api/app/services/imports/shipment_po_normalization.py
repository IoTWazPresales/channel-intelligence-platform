"""Purchase order number normalisation for shipment / lineup PO materialization."""

from __future__ import annotations

import re

_PO_PREFIX_RE = re.compile(r"^(?:PO[-_\s]?|INV[-_\s]?)", re.IGNORECASE)


def normalize_po_number(raw: str | None) -> str:
    """Strip whitespace, common PO/INV prefixes, leading zeros (numeric only), uppercase."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = _PO_PREFIX_RE.sub("", s).strip()
    if not s:
        return ""
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s.upper()
