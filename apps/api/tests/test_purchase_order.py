"""Unit 2a — normalize_po_number + PurchaseOrder model."""

from __future__ import annotations

import secrets

from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimDistributor
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_po_normalization import normalize_po_number
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE


def test_normalize_po_number_cases():
    assert normalize_po_number("  po-00123  ") == "123"
    assert normalize_po_number("PO_00045") == "45"
    assert normalize_po_number("inv-7788") == "7788"
    assert normalize_po_number("abc-99") == "ABC-99"
    assert normalize_po_number(None) == ""
    assert normalize_po_number("   ") == ""


def test_purchase_order_model_round_trip():
    import pytest

    token = secrets.token_hex(4)
    raw = f"PO-{token.upper()}"
    norm = normalize_po_number(raw)
    po_id: int | None = None
    try:
        with SessionLocal() as db:
            assert db.scalar(text("SELECT current_database()")) == "cip"
            if db.scalar(text("SELECT to_regclass('public.purchase_order')")) is None:
                pytest.skip("purchase_order table not migrated (20260628_0053)")
            dist_id = db.scalar(
                select(DimDistributor.id).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
            )
            assert dist_id is not None
            row = PurchaseOrder(
                po_number_raw=raw,
                po_number_norm=norm,
                distributor_id=int(dist_id),
                status="observed",
                source="shipment_materialized",
            )
            db.add(row)
            db.commit()
            po_id = int(row.id)

        with SessionLocal() as db:
            loaded = db.get(PurchaseOrder, po_id)
            assert loaded is not None
            assert loaded.po_number_raw == raw
            assert loaded.po_number_norm == norm
            assert loaded.status == "observed"
            assert loaded.source == "shipment_materialized"
    finally:
        if po_id is not None:
            with SessionLocal() as db:
                db.execute(text("DELETE FROM purchase_order WHERE id = :pid"), {"pid": po_id})
                db.commit()
