"""Materialize ``purchase_order`` rows from shipment evidence ``customer_po`` on validate."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_po_normalization import normalize_po_number


def upsert_observed_purchase_order(
    db: Session,
    *,
    po_number_raw: str,
    po_number_norm: str,
    distributor_id: int | None,
) -> int:
    """Insert observed PO or touch ``updated_at`` on existing (po_number_norm, distributor_id)."""
    tbl = PurchaseOrder.__table__
    ins = pg_insert(tbl).values(
        po_number_raw=po_number_raw[:128],
        po_number_norm=po_number_norm[:128],
        distributor_id=distributor_id,
        status="observed",
        source="shipment_materialized",
    )
    stmt = (
        ins.on_conflict_do_update(
            constraint="uq_purchase_order_norm_distributor",
            set_={
                "po_number_raw": ins.excluded.po_number_raw,
                "updated_at": func.now(),
            },
        )
        .returning(tbl.c.id)
    )
    rid = db.execute(stmt).scalar_one()
    return int(rid)


def materialize_purchase_orders_for_shipment_job(db: Session, import_job_id: int) -> int:
    """Link ``customer_po`` lines to ``purchase_order``; returns lines updated."""
    jid = int(import_job_id)
    lines = list(
        db.scalars(
            select(ShipmentEvidenceLine).where(
                ShipmentEvidenceLine.import_job_id == jid,
                ShipmentEvidenceLine.customer_po.is_not(None),
            )
        ).all()
    )
    updated = 0
    for line in lines:
        raw = (line.customer_po or "").strip()
        if not raw:
            continue
        norm = normalize_po_number(raw)
        if not norm:
            continue
        po_id = upsert_observed_purchase_order(
            db,
            po_number_raw=raw,
            po_number_norm=norm,
            distributor_id=int(line.distributor_id) if line.distributor_id is not None else None,
        )
        if line.purchase_order_id != po_id:
            line.purchase_order_id = po_id
            db.add(line)
            updated += 1
    db.flush()
    return updated
