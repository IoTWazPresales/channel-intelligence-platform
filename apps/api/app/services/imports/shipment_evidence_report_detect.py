"""Shipment report detection helpers (no database / SQLAlchemy imports)."""

from __future__ import annotations

import math
import re
from typing import Any

REPORT_XXOMRPT0025 = "xxomrpt0025_shipment"
REPORT_XXOMRPT0027 = "xxomrpt0027_order"
REPORT_ACZA_SHIPPED = "acza_workbook_shipped"
REPORT_ACZA_UNSHIP = "acza_workbook_unship"
REPORT_UNKNOWN = "unknown"

LINE_SHIPPED = "shipped"
LINE_OPEN_ORDER = "open_order"


def detect_report_type(columns: set[str], *, sheet_name: str | None, file_name: str) -> tuple[str, str]:
    """Return (report_type, line_state). Column names are compared case-insensitively."""
    _ = file_name
    sn = (sheet_name or "").strip().lower()
    c = {str(x).strip().lower() for x in columns}

    if "operating unit" in c and "delivery no" in c and "invoice line" in c:
        return REPORT_XXOMRPT0025, LINE_SHIPPED
    if "ou name" in c and "order no." in c:
        return REPORT_XXOMRPT0027, LINE_OPEN_ORDER
    if sn == "shipped" and "invoice line" in c and "sales model name" in c:
        return REPORT_ACZA_SHIPPED, LINE_SHIPPED
    if sn == "unship" or ("pi status" in c and "plan etd/eta durban" in c):
        return REPORT_ACZA_UNSHIP, LINE_OPEN_ORDER
    if "invoice line" in c and "sales model name" in c and "delivery no" in c:
        return REPORT_ACZA_SHIPPED, LINE_SHIPPED
    if "order no." in c and "sales model name" in c and "item" in c:
        return REPORT_ACZA_UNSHIP, LINE_OPEN_ORDER
    return REPORT_UNKNOWN, LINE_OPEN_ORDER


def _ean_upc_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, str):
        t = re.sub(r"\s+", "", v.strip())
        return t or None
    if isinstance(v, int):
        return str(int(v))
    if isinstance(v, float):
        if v == int(v):
            s = str(int(v))
            return s if s else None
        t = f"{v:.0f}"
        return t or None
    return str(v).strip() or None
