"""Stable ``source_key`` fragments per ``report_type`` for shipment evidence imports.

The import pipeline composes the stored key as ``{report_type}:{business_fragment}`` (length-capped).
That prefix is **generic** (same rule for every template) so keys from different extractors never collide
within one job when business tokens overlap.

Per-report business keys (minimal stable fields, not row position):

* **xxomrpt0025_shipment** — Oracle OM-style shipped extract: ``Operating Unit``, ``Delivery No``,
  and ``Invoice Line`` identify one shipped line; ``Item`` is appended so duplicate delivery/line
  combinations with different products stay distinct (rare but safe).

* **xxomrpt0027_order** — Open-order extract: ``OU NAME`` (mapped to ``operating_unit``),
  ``Order No.``, ``Order Line``, and ``Item`` identify one order line in the workbook.

* **acza_workbook_shipped** — Same canonical columns as the XXOMRPT shipped shape in
  ``_extract_common`` (delivery + invoice line + OU + item). Chosen because detection matches
  shipped logistics rows that carry ``Delivery No`` / ``Invoice Line``.

* **acza_workbook_unship** — Open pipeline sheet: ``Order No.``, ``Order Line``, ``Item`` plus
  ``operating_unit`` when present, matching the unship column set used in detection.

When all business segments are empty, a deterministic digest of the extracted dict is used so
re-import remains stable for odd rows without inventing positional keys.

New ``report_type`` values: register a builder in ``_BUSINESS_KEY_BY_REPORT`` and document the
key rationale in this module docstring.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from app.services.imports.shipment_evidence_report_detect import (
    REPORT_ACZA_SHIPPED,
    REPORT_ACZA_UNSHIP,
    REPORT_XXOMRPT0025,
    REPORT_XXOMRPT0027,
)


def _norm_seg(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s[:512]


def _pipe(*parts: Any) -> str:
    segs = [_norm_seg(p) for p in parts]
    segs = [s for s in segs if s]
    return "|".join(segs)


def _digest_ex(ex: dict[str, Any]) -> str:
    """Stable fallback when no business segments are present."""
    keys = sorted(ex.keys())
    slim = {k: ex.get(k) for k in keys}
    blob = json.dumps(slim, default=str, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _business_shipment_om(ex: dict[str, Any]) -> str:
    """Shipped / delivery-backed rows: OU + delivery + invoice line + item."""
    body = _pipe(
        ex.get("operating_unit"),
        ex.get("delivery_no"),
        ex.get("invoice_line"),
        ex.get("item_code"),
    )
    return body if body else f"digest:{_digest_ex(ex)}"


def _business_order_om(ex: dict[str, Any]) -> str:
    """Order / open-order rows: OU + order + line + item."""
    body = _pipe(
        ex.get("operating_unit"),
        ex.get("order_no"),
        ex.get("order_line"),
        ex.get("item_code"),
    )
    return body if body else f"digest:{_digest_ex(ex)}"


_BUSINESS_KEY_BY_REPORT: dict[str, Callable[[dict[str, Any]], str]] = {
    REPORT_XXOMRPT0025: _business_shipment_om,
    REPORT_ACZA_SHIPPED: _business_shipment_om,
    REPORT_XXOMRPT0027: _business_order_om,
    REPORT_ACZA_UNSHIP: _business_order_om,
}


class ShipmentEvidenceSourceKeyError(ValueError):
    """Raised when ``report_type`` has no registered business-key builder."""


def business_source_key_fragment(report_type: str, ex: dict[str, Any]) -> str:
    """Return the report-specific business fragment (no ``report_type`` prefix)."""
    fn = _BUSINESS_KEY_BY_REPORT.get(report_type)
    if fn is None:
        raise ShipmentEvidenceSourceKeyError(
            f"No source_key builder registered for report_type={report_type!r}. "
            "Add one in shipment_evidence_source_keys._BUSINESS_KEY_BY_REPORT."
        )
    return fn(ex)


def stable_source_key_for_row(*, report_type: str, sheet_name: str | None, ex: dict[str, Any]) -> str:
    """Full ``source_key`` stored on ``ShipmentEvidenceLine`` (max 256 chars, unique per job)."""
    biz = business_source_key_fragment(report_type, ex)
    if sheet_name and str(sheet_name).strip():
        biz = f"{_norm_seg(sheet_name)}|{biz}"
    combined = f"{report_type}:{biz}"
    if len(combined) <= 256:
        return combined
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:48]
    out = f"{report_type}:h{digest}"
    return out[:256]
