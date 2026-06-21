"""Upsert ``fact_inbound_shipment`` from ``ShipmentEvidenceLine`` (inbound apply truth layer)."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.utils.json_safe import to_jsonable

# Columns refreshed on ``ON CONFLICT (source_key) DO UPDATE`` — every mutable column
# (i.e. all of them except the surrogate ``id``, the conflict key ``source_key``, and
# ``created_at``). ``updated_at`` is set to ``now()`` separately. Latest-job-wins is
# preserved because ``import_job_id`` is among the refreshed columns.
_UPSERT_REFRESH_COLUMNS: tuple[str, ...] = (
    "import_job_id",
    "shipment_evidence_line_id",
    "source_sheet",
    "source_row_number",
    "report_type",
    "line_state",
    "raw_source_row",
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
    "product_id",
    "product_resolution_status",
    "product_resolution_token",
    "product_resolution_detail",
    "distributor_id",
    "distributor_resolution_status",
    "distributor_resolution_token",
    "customer_dealer_token",
    "customer_id",
    "customer_resolution_status",
    "eta_date",
    "reference",
    "status",
)

# Rows per multi-values INSERT. ~45 bound columns/row keeps each statement well under
# Postgres' 65535-parameter limit (500 × 45 ≈ 22.5k) while collapsing the former
# per-row round-trips into a handful of statements.
_UPSERT_CHUNK_SIZE = 500


def _coalesce_shipment_dates(line: ShipmentEvidenceLine) -> date | None:
    """Match apply-path rule: first non-null among the seven logistics dates (pod-first)."""
    for d in (
        line.pod_date,
        line.est_pod_date,
        line.promise_date,
        line.schedule_ship_date,
        line.ship_confirm_date,
        line.erd_date,
        line.exwork_date,
    ):
        if d is not None:
            return d
    return None


def _derive_inbound_status(line: ShipmentEvidenceLine) -> str:
    return "received" if line.pod_date is not None else "scheduled"


def _row_values_from_evidence(line: ShipmentEvidenceLine) -> dict[str, Any]:
    eta = _coalesce_shipment_dates(line)
    raw = line.raw_source_row if isinstance(line.raw_source_row, dict) else {}
    return {
        "import_job_id": int(line.import_job_id),
        "source_key": line.source_key,
        "shipment_evidence_line_id": int(line.id),
        "source_sheet": line.source_sheet,
        "source_row_number": int(line.source_row_number),
        "report_type": line.report_type,
        "line_state": line.line_state,
        "raw_source_row": to_jsonable(raw),
        "operating_unit": line.operating_unit,
        "bill_to_raw": line.bill_to_raw,
        "ship_to_raw": line.ship_to_raw,
        "order_no": line.order_no,
        "order_line": line.order_line,
        "delivery_no": line.delivery_no,
        "invoice_line": line.invoice_line,
        "item_code": line.item_code,
        "sales_model_name": line.sales_model_name,
        "customer_item": line.customer_item,
        "ean_code": line.ean_code,
        "upc_code": line.upc_code,
        "mpor_item_no": line.mpor_item_no,
        "quantity": float(line.quantity) if line.quantity is not None else None,
        "unit_price": float(line.unit_price) if line.unit_price is not None else None,
        "amount": float(line.amount) if line.amount is not None else None,
        "currency_code": line.currency_code,
        "ship_confirm_date": line.ship_confirm_date,
        "schedule_ship_date": line.schedule_ship_date,
        "promise_date": line.promise_date,
        "exwork_date": line.exwork_date,
        "erd_date": line.erd_date,
        "est_pod_date": line.est_pod_date,
        "pod_date": line.pod_date,
        "product_id": int(line.product_id) if line.product_id is not None else None,
        "product_resolution_status": line.product_resolution_status,
        "product_resolution_token": line.product_resolution_token,
        "product_resolution_detail": line.product_resolution_detail,
        "distributor_id": int(line.distributor_id) if line.distributor_id is not None else None,
        "distributor_resolution_status": line.distributor_resolution_status,
        "distributor_resolution_token": line.distributor_resolution_token,
        "customer_dealer_token": line.customer_dealer_token,
        "customer_id": int(line.customer_id) if line.customer_id is not None else None,
        "customer_resolution_status": line.customer_resolution_status,
        "eta_date": eta,
        "reference": line.order_no,
        "status": _derive_inbound_status(line),
    }


def _conflict_update_set(ins: Any) -> dict[str, Any]:
    """``ON CONFLICT DO UPDATE`` SET map: refresh every mutable column from the proposed row."""
    ex = ins.excluded
    set_ = {col: getattr(ex, col) for col in _UPSERT_REFRESH_COLUMNS}
    set_["updated_at"] = func.now()
    return set_


def upsert_inbound_shipment_facts_for_job(
    db: Session,
    import_job_id: int,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = _UPSERT_CHUNK_SIZE,
) -> int:
    """Insert/update ``fact_inbound_shipment`` for every evidence line on the job (``ON CONFLICT (source_key)``).

    Writes are batched into chunked multi-row statements (``chunk_size`` rows each) instead of
    one round-trip per line — the same N+1 fix applied to validate/steward. ``on_progress`` is
    invoked after each chunk with ``(rows_written_so_far, total_rows)`` for background-task UI.
    """
    lines = list(
        db.scalars(
            select(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.import_job_id == int(import_job_id))
            .order_by(ShipmentEvidenceLine.id)
        ).all()
    )
    total = len(lines)
    tbl = FactInboundShipment.__table__
    n = 0
    for start in range(0, total, chunk_size):
        chunk = lines[start : start + chunk_size]
        rows = [_row_values_from_evidence(line) for line in chunk]
        ins = pg_insert(tbl).values(rows)
        stmt = ins.on_conflict_do_update(
            constraint="uq_fact_inbound_shipment_source_key",
            set_=_conflict_update_set(ins),
        )
        db.execute(stmt)
        n += len(chunk)
        if on_progress is not None:
            on_progress(n, total)
    db.flush()
    return n
