"""Unit 1 — customer_po distinct from order_no on shipment evidence extract."""

from __future__ import annotations

import pandas as pd

from app.services.imports.shipment_field_mapping import (
    SHIPMENT_CANONICAL_TARGETS,
    build_initial_shipment_field_mapping,
)
from app.services.imports.shipment_evidence_import import _extract_common


def test_order_no_and_customer_po_alias_sets_do_not_collide():
    order_aliases = {
        "order no.",
        "order no",
        "order number",
        "order_no",
    }
    po_aliases = {
        "customer po",
        "cust po",
        "customer p/o",
        "purchase order",
        "po no",
        "po no.",
        "po number",
        "customer_po",
    }
    assert order_aliases.isdisjoint(po_aliases)
    assert "customer_po" in SHIPMENT_CANONICAL_TARGETS
    assert "order_no" in SHIPMENT_CANONICAL_TARGETS


def test_extract_common_populates_order_no_and_customer_po_distinctly():
    headers = ["Order No.", "Customer PO", "Item"]
    mapping = build_initial_shipment_field_mapping(headers, source=None)
    assert mapping["Order No."] == "order_no"
    assert mapping["Customer PO"] == "customer_po"

    header_by_canonical = {v: k for k, v in mapping.items()}
    row = pd.Series(
        {
            "Order No.": "ASUS-ORD-9001",
            "Customer PO": "DIST-PO-4422",
            "Item": "SKU-1",
        }
    )
    ex = _extract_common(row, header_by_canonical=header_by_canonical)
    assert ex["order_no"] == "ASUS-ORD-9001"
    assert ex["customer_po"] == "DIST-PO-4422"
    assert ex["order_no"] != ex["customer_po"]
