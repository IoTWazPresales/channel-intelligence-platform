"""Backfill script — dry-run safe; confirm path when schema migrated."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from scripts.backfill_shipment_customer_po import run


def _require_schema(db) -> None:
    if db.scalar(text("SELECT to_regclass('public.purchase_order')")) is None:
        pytest.skip("purchase_order schema not migrated (0053+)")
    cols = {
        r[0]
        for r in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'shipment_evidence_line' "
                "AND column_name IN ('customer_po', 'purchase_order_id')"
            )
        )
    }
    if cols != {"customer_po", "purchase_order_id"}:
        pytest.skip("shipment customer_po / purchase_order_id columns not migrated (0052+0054)")


def test_backfill_dry_run_writes_nothing():
    token = secrets.token_hex(4)
    job_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert source_id
            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"bf_dry_{token}.csv",
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
                    source_key=f"bf-dry-{token}",
                    raw_source_row={"Customer PO": "PO-5555", "Item": "Z"},
                    product_resolution_status="no_identifier",
                    distributor_resolution_status="unresolved",
                )
            )
            db.commit()

        stats = run(confirm=False)
        assert stats["customer_po_found"] >= 1

        with SessionLocal() as db:
            line = db.scalar(
                select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == job_id)
            )
            assert line is not None
            assert line.customer_po is None
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


def test_backfill_missing_po_column_stays_null():
    token = secrets.token_hex(4)
    job_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert source_id
            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"bf_miss_{token}.csv",
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
                    source_key=f"bf-miss-{token}",
                    raw_source_row={"Order No.": "INT-9", "Item": "Z"},
                    product_resolution_status="no_identifier",
                    distributor_resolution_status="unresolved",
                )
            )
            db.commit()

        stats = run(confirm=True)
        assert stats["no_po_column"] >= 1

        with SessionLocal() as db:
            line = db.scalar(
                select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == job_id)
            )
            assert line is not None
            assert line.customer_po is None
    finally:
        if job_id is not None:
            with SessionLocal() as db:
                db.execute(
                    text("DELETE FROM shipment_evidence_line WHERE import_job_id = :jid"),
                    {"jid": job_id},
                )
                db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": job_id})
                db.commit()


def test_backfill_confirm_updates_and_dedupes_normalized_po():
    token = secrets.token_hex(4)
    job_id: int | None = None
    try:
        with SessionLocal() as db:
            _require_schema(db)
            source_id = db.scalar(
                select(SourceDefinition.id).where(SourceDefinition.code == "inbound_default")
            )
            assert source_id
            job = ImportJob(
                source_id=int(source_id),
                template_slug="inbound_shipments",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=f"bf_dup_{token}.csv",
            )
            db.add(job)
            db.flush()
            job_id = int(job.id)
            for i, po in enumerate(("PO-0077", "po-00077"), start=1):
                db.add(
                    ShipmentEvidenceLine(
                        import_job_id=job_id,
                        source_row_number=i,
                        report_type="shipped",
                        line_state="shipped",
                        source_key=f"bf-dup-{token}-{i}",
                        raw_source_row={"Customer PO": po, "Item": f"Z{i}"},
                        product_resolution_status="no_identifier",
                        distributor_resolution_status="unresolved",
                    )
                )
            db.commit()

        stats = run(confirm=True)
        assert stats["lines_updated"] >= 2

        with SessionLocal() as db:
            lines = list(
                db.scalars(
                    select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == job_id)
                ).all()
            )
            assert len(lines) == 2
            assert all(l.customer_po is not None for l in lines)
            po_ids = {l.purchase_order_id for l in lines}
            assert len(po_ids) == 1
            n_po = db.scalar(
                select(func.count())
                .select_from(PurchaseOrder)
                .where(PurchaseOrder.po_number_norm == "77")
            )
            assert int(n_po or 0) == 1
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
                    {"n": "77"},
                )
                db.commit()
