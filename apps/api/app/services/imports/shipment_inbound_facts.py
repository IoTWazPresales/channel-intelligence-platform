"""Upsert ``fact_inbound_shipment`` from ``ShipmentEvidenceLine`` (inbound apply truth layer)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Callable

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_evidence_line_identity import fact_upsert_key_for_evidence_values
from app.utils.json_safe import to_jsonable

# Columns refreshed on ``ON CONFLICT (fact_upsert_key) DO UPDATE`` — every mutable column
# except ``id``, ``fact_upsert_key``, and ``created_at``. ``source_key`` is refreshed from the
# latest evidence row (per-job lineage); conflict identity is ``fact_upsert_key`` (shipped-stable
# or open-order ``source_key``). Latest-job-wins via ``import_job_id``.
_UPSERT_REFRESH_COLUMNS: tuple[str, ...] = (
    "import_job_id",
    "source_key",
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
    "customer_po",
    "purchase_order_id",
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
    "crad_date",
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
    "resolved_customer_id",
    "resolved_distributor_id",
    "eta_date",
    "reference",
    "status",
)

_UPSERT_CHUNK_SIZE = 500
_FACT_UPSERT_CONSTRAINT = "uq_fact_inbound_shipment_fact_upsert_key"
_SOURCE_KEY_CONSTRAINT = "uq_fact_inbound_shipment_source_key"


def _coalesce_shipment_dates(line: ShipmentEvidenceLine) -> date | None:
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
    base = {
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
        "customer_po": line.customer_po,
        "purchase_order_id": int(line.purchase_order_id) if line.purchase_order_id is not None else None,
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
        "crad_date": line.crad_date,
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
        "resolved_customer_id": int(line.resolved_customer_id) if line.resolved_customer_id is not None else None,
        "resolved_distributor_id": int(line.resolved_distributor_id)
        if line.resolved_distributor_id is not None
        else None,
        "eta_date": eta,
        "reference": line.order_no,
        "status": _derive_inbound_status(line),
    }
    base["fact_upsert_key"] = fact_upsert_key_for_evidence_values(base)
    return base


def _merge_shipped_row_into(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Sum measures for duplicate shipped ``fact_upsert_key`` within one apply batch."""
    for measure in ("quantity", "amount"):
        t = target.get(measure)
        i = incoming.get(measure)
        if t is not None or i is not None:
            target[measure] = float(t or 0) + float(i or 0)
    for col in _UPSERT_REFRESH_COLUMNS:
        if col in ("quantity", "amount"):
            continue
        if col in incoming:
            target[col] = incoming[col]


def _dedupe_rows_for_fact_upsert(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows sharing ``fact_upsert_key`` within a chunk (shipped sums qty)."""
    order: list[str] = []
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["fact_upsert_key"])
        if key not in by_key:
            by_key[key] = dict(row)
            order.append(key)
            continue
        existing = by_key[key]
        if (existing.get("line_state") or "").strip().lower() == "shipped" and (
            row.get("line_state") or ""
        ).strip().lower() == "shipped":
            _merge_shipped_row_into(existing, row)
        else:
            by_key[key] = dict(row)
    return [by_key[k] for k in order]


def _conflict_update_set(ins: Any) -> dict[str, Any]:
    ex = ins.excluded
    set_ = {col: getattr(ex, col) for col in _UPSERT_REFRESH_COLUMNS}
    set_["updated_at"] = func.now()
    return set_


def _upsert_open_order_chunk(db: Session, tbl: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    ins = pg_insert(tbl).values(rows)
    stmt = ins.on_conflict_do_update(
        constraint=_SOURCE_KEY_CONSTRAINT,
        set_=_conflict_update_set(ins),
    )
    db.execute(stmt)


def _upsert_shipped_chunk(db: Session, tbl: Any, rows: list[dict[str, Any]]) -> None:
    """Replace shipped facts by stable ``fact_upsert_key`` (latest job wins for the chunk)."""
    if not rows:
        return
    aggregated = _dedupe_rows_for_fact_upsert(rows)
    keys = [str(r["fact_upsert_key"]) for r in aggregated]
    db.execute(delete(FactInboundShipment).where(FactInboundShipment.fact_upsert_key.in_(keys)))
    db.execute(pg_insert(tbl).values(aggregated))


def upsert_inbound_shipment_facts_for_job(
    db: Session,
    import_job_id: int,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = _UPSERT_CHUNK_SIZE,
) -> int:
    """Insert/update ``fact_inbound_shipment`` for every evidence line on the job.

    Shipped rows replace by PO-inclusive ``fact_upsert_key`` (invoice lines within PO sum).
    keep per-job ``source_key`` upsert semantics.
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
        row_values = [_row_values_from_evidence(line) for line in chunk]
        shipped_rows = [r for r in row_values if (r.get("line_state") or "").strip().lower() == "shipped"]
        open_rows = [r for r in row_values if (r.get("line_state") or "").strip().lower() != "shipped"]
        _upsert_shipped_chunk(db, tbl, shipped_rows)
        _upsert_open_order_chunk(db, tbl, open_rows)
        n += len(chunk)
        if on_progress is not None:
            on_progress(n, total)
    db.flush()
    return n
