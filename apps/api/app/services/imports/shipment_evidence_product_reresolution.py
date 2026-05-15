"""Batch re-run shipment evidence product resolution after catalog changes (e.g. PM commit)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import _load_product_resolution_index
from app.services.imports.shipment_evidence_import import resolve_product_for_evidence

ProgressCb = Callable[[dict[str, Any]], None]


def count_all_shipment_evidence_lines(db: Session) -> int:
    n = db.scalar(select(func.count()).select_from(ShipmentEvidenceLine))
    return int(n or 0)


def rerun_shipment_product_resolution_all_lines(
    db: Session,
    *,
    on_progress: ProgressCb | None = None,
    commit_every: int = 250,
    fetch_batch_size: int = 500,
) -> dict[str, Any]:
    """Re-resolve products for every row in ``shipment_evidence_line``. Commits periodically."""
    idx = _load_product_resolution_index(db)
    total = count_all_shipment_evidence_lines(db)
    processed = 0
    newly_resolved = 0
    still_unresolved = 0

    def _emit() -> None:
        if on_progress:
            on_progress(
                {
                    "lines_total": total,
                    "lines_processed": processed,
                    "newly_resolved": newly_resolved,
                    "still_unresolved": still_unresolved,
                }
            )

    _emit()

    if total == 0:
        return {
            "lines_total": 0,
            "lines_processed": 0,
            "newly_resolved": 0,
            "still_unresolved": 0,
        }

    last_id = 0
    while True:
        lines = db.scalars(
            select(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.id > last_id)
            .order_by(ShipmentEvidenceLine.id)
            .limit(fetch_batch_size)
        ).all()
        if not lines:
            break

        for line in lines:
            last_id = int(line.id)
            old_status = (line.product_resolution_status or "").strip()
            pid, pstatus, ptoken, pdetail = resolve_product_for_evidence(
                idx,
                item_code=line.item_code,
                ean_code=line.ean_code,
                upc_code=line.upc_code,
                sales_model_name=line.sales_model_name,
            )
            line.product_id = pid
            line.product_resolution_status = pstatus
            line.product_resolution_token = ptoken
            line.product_resolution_detail = pdetail
            db.add(line)

            processed += 1
            if old_status != "resolved_unique" and pstatus == "resolved_unique":
                newly_resolved += 1
            if pstatus != "resolved_unique":
                still_unresolved += 1

            if commit_every > 0 and processed % commit_every == 0:
                db.commit()
                _emit()

    db.commit()
    _emit()
    return {
        "lines_total": total,
        "lines_processed": processed,
        "newly_resolved": newly_resolved,
        "still_unresolved": still_unresolved,
    }
