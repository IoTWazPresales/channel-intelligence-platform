"""Unit 2c — materialize purchase_order from shipment customer_po on validate."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE
from app.services.imports.shipment_field_mapping import extract_customer_po_from_raw_row
from app.services.imports.shipment_purchase_order_materialize import materialize_purchase_orders_for_shipment_job
from app.models.dimensions import DimDistributor


def _require_po_schema(db) -> None:
    if db.scalar(text("SELECT to_regclass('public.purchase_order')")) is None:
        pytest.skip("purchase_order schema not migrated (0053+)")
    cols = {
        r[0]
        for r in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'shipment_evidence_line' AND column_name IN "
                "('customer_po', 'purchase_order_id', 'resolved_customer_id', "
                "'resolved_distributor_id', 'crad_date')"
            )
        )
    }
    if "customer_po" not in cols or "purchase_order_id" not in cols:
        pytest.skip("shipment customer_po / purchase_order_id columns not migrated (0052+0054)")
    if not {"resolved_customer_id", "resolved_distributor_id", "crad_date"}.issubset(cols):
        pytest.skip("shipment resolved_* / crad_date columns not migrated (0058)")


def test_extract_customer_po_from_raw_row():
    raw = {"Order No.": "INT-1", "Customer PO": "PO-ABC-99"}
    assert extract_customer_po_from_raw_row(raw) == "PO-ABC-99"
    assert extract_customer_po_from_raw_row({"Order No.": "INT-1"}) is None


def test_materialize_purchase_order_from_customer_po():
    token = secrets.token_hex(4)
    job_id: int | None = None
    line_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_po_schema(db)
            dist_id = db.scalar(
                select(DimDistributor.id).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
            )
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert dist_id and source_id

            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"po_mat_{token}.csv",
            )
            db.add(job)
            db.flush()
            job_id = int(job.id)

            line = ShipmentEvidenceLine(
                import_job_id=job_id,
                source_row_number=1,
                report_type="shipped",
                line_state="shipped",
                source_key=f"test-po-mat-{token}",
                raw_source_row={"Item": "X"},
                customer_po="PO-00123",
                distributor_id=int(dist_id),
                resolved_distributor_id=int(dist_id),
                product_resolution_status="no_identifier",
                distributor_resolution_status="resolved",
            )
            db.add(line)
            db.commit()
            line_id = int(line.id)

        with SessionLocal() as db:
            materialize_purchase_orders_for_shipment_job(db, int(job_id))
            db.commit()
            n_po = db.scalar(select(func.count()).select_from(PurchaseOrder))
            assert int(n_po or 0) >= 1
            line = db.get(ShipmentEvidenceLine, line_id)
            assert line is not None
            assert line.purchase_order_id is not None

        with SessionLocal() as db:
            before = db.scalar(select(func.count()).select_from(PurchaseOrder))
            materialize_purchase_orders_for_shipment_job(db, int(job_id))
            db.commit()
            after = db.scalar(select(func.count()).select_from(PurchaseOrder))
            assert after == before
    finally:
        if job_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE import_job_id = :jid"),
                    {"jid": job_id},
                )
                db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": job_id})
                db.execute(
                    text("DELETE FROM purchase_order WHERE po_number_norm = :n"),
                    {"n": "123"},
                )
                db.commit()


def test_no_customer_po_does_not_create_purchase_order():
    token = secrets.token_hex(4)
    job_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_po_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert source_id
            before = int(db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0)
            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"po_none_{token}.csv",
            )
            db.add(job)
            db.flush()
            job_id = int(job.id)
            db.add(
                ShipmentEvidenceLine(
                    import_job_id=job_id,
                    source_row_number=1,
                    report_type="shipped",
                    line_state="shipped",
                    source_key=f"test-po-none-{token}",
                    raw_source_row={"Item": "Y"},
                    customer_po=None,
                    product_resolution_status="no_identifier",
                    distributor_resolution_status="unresolved",
                )
            )
            db.commit()
            materialize_purchase_orders_for_shipment_job(db, job_id)
            db.commit()
            after = int(db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0)
            assert after == before
    finally:
        if job_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE import_job_id = :jid"),
                    {"jid": job_id},
                )
                db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": job_id})
                db.commit()


def test_materialize_defers_when_resolved_distributor_null():
    """Unit 2 — do not mint NULL-keyed purchase_order when distributor unresolved."""
    token = secrets.token_hex(4)
    job_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_po_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert source_id
            before = int(db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0)
            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"po_defer_{token}.csv",
            )
            db.add(job)
            db.flush()
            job_id = int(job.id)
            db.add(
                ShipmentEvidenceLine(
                    import_job_id=job_id,
                    source_row_number=1,
                    report_type="shipped",
                    line_state="shipped",
                    source_key=f"test-po-defer-{token}",
                    raw_source_row={"Item": "Z"},
                    customer_po="PO-DEFER-999",
                    distributor_id=None,
                    resolved_distributor_id=None,
                    product_resolution_status="no_identifier",
                    distributor_resolution_status="unresolved",
                )
            )
            db.commit()
            materialize_purchase_orders_for_shipment_job(db, job_id)
            db.commit()
            after = int(db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0)
            assert after == before
            line = db.scalars(
                select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == job_id)
            ).first()
            assert line is not None
            assert line.purchase_order_id is None
    finally:
        if job_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE import_job_id = :jid"),
                    {"jid": job_id},
                )
                db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": job_id})
                db.commit()
