"""Stable ``line_identity_key`` for bitemporal shipment evidence (Plan D / BACKLOG-033).

Distinct from per-job ``source_key``: identity is scoped to business dimensions that
should remain stable across open-order → shipped lifecycle transitions within one OU.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.imports.shipment_evidence_source_keys import _digest_ex, _norm_seg, _pipe


def stable_line_identity_key_from_fields(
    *,
    operating_unit: Any = None,
    order_no: Any = None,
    order_line: Any = None,
    delivery_no: Any = None,
    invoice_line: Any = None,
    item_code: Any = None,
    raw_source_row: dict[str, Any] | None = None,
) -> str:
    """Return a business-stable identity key (max 256 chars)."""
    ex = {
        "operating_unit": operating_unit,
        "order_no": order_no,
        "order_line": order_line,
        "delivery_no": delivery_no,
        "invoice_line": invoice_line,
        "item_code": item_code,
    }
    order_body = _pipe(
        ex.get("operating_unit"),
        ex.get("order_no"),
        ex.get("order_line"),
        ex.get("item_code"),
    )
    if order_body and _norm_seg(ex.get("order_no")):
        key = f"order:{order_body}"
    else:
        ship_body = _pipe(
            ex.get("operating_unit"),
            ex.get("delivery_no"),
            ex.get("invoice_line"),
            ex.get("item_code"),
        )
        if ship_body and (
            _norm_seg(ex.get("delivery_no")) or _norm_seg(ex.get("invoice_line"))
        ):
            key = f"ship:{ship_body}"
        elif raw_source_row:
            key = f"digest:{_digest_ex(raw_source_row)}"
        else:
            key = f"digest:{_digest_ex(ex)}"
    return key[:256]


def stable_line_identity_key_from_mapping(values: dict[str, Any]) -> str:
    """Derive identity from a shipment evidence row dict."""
    return stable_line_identity_key_from_fields(
        operating_unit=values.get("operating_unit"),
        order_no=values.get("order_no"),
        order_line=values.get("order_line"),
        delivery_no=values.get("delivery_no"),
        invoice_line=values.get("invoice_line"),
        item_code=values.get("item_code"),
        raw_source_row=values.get("raw_source_row")
        if isinstance(values.get("raw_source_row"), dict)
        else None,
    )


_OBSERVATION_HASH_COLS = (
    "source_sheet",
    "source_row_number",
    "report_type",
    "line_state",
    "source_key",
    "line_identity_key",
    "operating_unit",
    "bill_to_raw",
    "ship_to_raw",
    "order_no",
    "order_line",
    "delivery_no",
    "invoice_line",
    "item_code",
    "sales_model_name",
    "customer_item",
    "ean_code",
    "upc_code",
    "mpor_item_no",
    "quantity",
    "unit_price",
    "amount",
    "currency_code",
    "ship_confirm_date",
    "schedule_ship_date",
    "promise_date",
    "exwork_date",
    "erd_date",
    "est_pod_date",
    "pod_date",
    "customer_dealer_token",
    "customer_id",
    "customer_resolution_status",
    "product_id",
    "product_resolution_status",
    "product_resolution_token",
    "product_resolution_detail",
    "distributor_id",
    "distributor_resolution_status",
    "distributor_resolution_token",
)


def observation_payload_hash(values: dict[str, Any]) -> str:
    """Deterministic hash for idempotent observation append per job."""
    slim = {k: values.get(k) for k in _OBSERVATION_HASH_COLS}
    blob = json.dumps(slim, default=str, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]
