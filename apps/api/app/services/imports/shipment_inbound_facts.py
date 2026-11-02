"""Upsert ``fact_inbound_shipment`` from ``ShipmentEvidenceLine`` (inbound apply truth layer)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date
from typing import Any, Callable

logger = logging.getLogger(__name__)

from sqlalchemy import case, delete, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_water import WATER_FIELDS
from app.services.imports.shipment_apply_failure import ShipmentApplyRowError
from app.services.imports.shipment_evidence_line_identity import fact_upsert_key_for_evidence_values
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    retire_orphaned_open_rows,
    retire_po_less_twins_written_by_job,
)
from app.services.shipment_live_line import live_line
from app.utils.json_safe import to_jsonable


def _sticky_pod(incoming: date | None, existing: date | None) -> date | None:
    """Once POD is observed, later null snapshots do not clear it (P1-D004 / BACKLOG-088)."""
    return incoming if incoming is not None else existing


def _status_for_pod(pod: date | None) -> str:
    return "received" if pod is not None else "scheduled"

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
    "tenant_id",
    # On the water (20261101_0049): copied from the evidence line, refreshed with it.
    *WATER_FIELDS,
)

_UPSERT_CHUNK_SIZE = 500
_FACT_UPSERT_CONSTRAINT = "uq_fact_inbound_shipment_fact_upsert_key"


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
    return _status_for_pod(line.pod_date)


def _row_values_from_evidence(line: ShipmentEvidenceLine, *, tenant_id: str = "default") -> dict[str, Any]:
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
        "tenant_id": (tenant_id or "default").strip() or "default",
        **{name: getattr(line, name, None) for name in WATER_FIELDS},
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
        if col == "pod_date":
            target[col] = _sticky_pod(incoming.get(col), target.get(col))
            continue
        if col == "status":
            continue
        if col in incoming:
            target[col] = incoming[col]
    target["status"] = _status_for_pod(target.get("pod_date"))


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
    """Open-order upsert: sticky POD (COALESCE incoming, existing) + aligned status."""
    ex = ins.excluded
    tbl = FactInboundShipment.__table__.c
    sticky_pod = func.coalesce(ex.pod_date, tbl.pod_date)
    set_ = {col: getattr(ex, col) for col in _UPSERT_REFRESH_COLUMNS if col not in ("pod_date", "status")}
    set_["pod_date"] = sticky_pod
    set_["status"] = case((sticky_pod.is_not(None), literal("received")), else_=literal("scheduled"))
    set_["updated_at"] = func.now()
    return set_


def _upsert_open_order_chunk(db: Session, tbl: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    ins = pg_insert(tbl).values(rows)
    stmt = ins.on_conflict_do_update(
        constraint=_FACT_UPSERT_CONSTRAINT,
        set_=_conflict_update_set(ins),
    )
    db.execute(stmt)


def _upsert_single_evidence_row(
    db: Session, tbl: Any, line: ShipmentEvidenceLine, *, tenant_id: str = "default"
) -> None:
    row_values = _row_values_from_evidence(line, tenant_id=tenant_id)
    line_state = (row_values.get("line_state") or "").strip().lower()
    if line_state == "shipped":
        _upsert_shipped_chunk(db, tbl, [row_values])
    else:
        _upsert_open_order_chunk(db, tbl, [row_values])


def _upsert_evidence_chunk(
    db: Session,
    tbl: Any,
    chunk: list[ShipmentEvidenceLine],
    row_values: list[dict[str, Any]],
    *,
    tenant_id: str = "default",
) -> None:
    shipped_rows = [r for r in row_values if (r.get("line_state") or "").strip().lower() == "shipped"]
    open_rows = [r for r in row_values if (r.get("line_state") or "").strip().lower() != "shipped"]
    try:
        _upsert_shipped_chunk(db, tbl, shipped_rows)
        _upsert_open_order_chunk(db, tbl, open_rows)
    except Exception as chunk_exc:
        for line in chunk:
            try:
                _upsert_single_evidence_row(db, tbl, line, tenant_id=tenant_id)
            except Exception as row_exc:
                raise ShipmentApplyRowError(
                    f"Fact write failed for evidence line {line.id}: {row_exc}",
                    evidence_line_id=int(line.id),
                    source_key=str(line.source_key or ""),
                    source_row_number=int(line.source_row_number) if line.source_row_number is not None else None,
                    cause=row_exc,
                ) from row_exc
        raise ShipmentApplyRowError(
            f"Fact write failed for chunk starting evidence line {chunk[0].id}: {chunk_exc}",
            evidence_line_id=int(chunk[0].id),
            source_key=str(chunk[0].source_key or ""),
            source_row_number=int(chunk[0].source_row_number)
            if chunk[0].source_row_number is not None
            else None,
            cause=chunk_exc,
        ) from chunk_exc


def _existing_pod_by_fact_keys(db: Session, keys: list[str]) -> dict[str, date]:
    if not keys:
        return {}
    rows = db.execute(
        select(FactInboundShipment.fact_upsert_key, FactInboundShipment.pod_date).where(
            FactInboundShipment.fact_upsert_key.in_(keys),
            FactInboundShipment.pod_date.is_not(None),
        )
    ).all()
    return {str(k): pod for k, pod in rows if pod is not None}


def _apply_sticky_pod_to_rows(rows: list[dict[str, Any]], prior_pod: dict[str, date]) -> None:
    for row in rows:
        key = str(row["fact_upsert_key"])
        row["pod_date"] = _sticky_pod(row.get("pod_date"), prior_pod.get(key))
        row["status"] = _status_for_pod(row.get("pod_date"))


def _upsert_shipped_chunk(db: Session, tbl: Any, rows: list[dict[str, Any]]) -> None:
    """Replace shipped facts by stable ``fact_upsert_key`` (latest job wins for the chunk).

    Sticky POD: if the incoming job omits ``pod_date`` but a prior fact for the same key
    had one, keep the prior POD (P1-D004). Status stays aligned with sticky POD.
    """
    if not rows:
        return
    aggregated = _dedupe_rows_for_fact_upsert(rows)
    keys = [str(r["fact_upsert_key"]) for r in aggregated]
    prior_pod = _existing_pod_by_fact_keys(db, keys)
    _apply_sticky_pod_to_rows(aggregated, prior_pod)
    db.execute(delete(FactInboundShipment).where(FactInboundShipment.fact_upsert_key.in_(keys)))
    db.execute(pg_insert(tbl).values(aggregated))


_GUARD_LOOKUP_BATCH = 2000


def _blank(value: Any) -> bool:
    return value is None or not str(value).strip()


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _closed_keys_among(db: Session, keys: list[str]) -> set[str]:
    """Fact keys (of ``keys``) whose fact is closed: the book already decided that line is gone."""
    found: set[str] = set()
    for i in range(0, len(keys), _GUARD_LOOKUP_BATCH):
        batch = keys[i : i + _GUARD_LOOKUP_BATCH]
        found.update(
            str(k)
            for k in db.scalars(
                select(FactInboundShipment.fact_upsert_key).where(
                    FactInboundShipment.fact_upsert_key.in_(batch),
                    ~live_line(FactInboundShipment.line_state),
                )
            ).all()
        )
    return found


def _open_line_identities_under_other_keys(
    db: Session, tenant_id: str, import_job_id: int, rows: list[dict[str, Any]]
) -> dict[tuple[str, str, str, str, str], set[str]]:
    """Open facts of OTHER jobs that carry the same order line as one of ``rows`` under a different key.

    The identity is report type + order + order line + item + operating unit. A row without an order line has no
    line identity and is never matched (an order + item can hold several lines).
    """
    wanted = {
        (r["report_type"], r["order_no"], r["order_line"], r["item_code"])
        for r in rows
        if not (_blank(r.get("order_no")) or _blank(r.get("order_line")) or _blank(r.get("item_code")))
    }
    out: dict[tuple[str, str, str, str, str], set[str]] = defaultdict(set)
    batch_list = list(wanted)
    for i in range(0, len(batch_list), _GUARD_LOOKUP_BATCH):
        batch = batch_list[i : i + _GUARD_LOOKUP_BATCH]
        found = db.execute(
            select(
                FactInboundShipment.report_type,
                FactInboundShipment.order_no,
                FactInboundShipment.order_line,
                FactInboundShipment.item_code,
                FactInboundShipment.operating_unit,
                FactInboundShipment.fact_upsert_key,
            ).where(
                FactInboundShipment.tenant_id == tenant_id,
                func.lower(func.coalesce(FactInboundShipment.line_state, "")) == "open_order",
                FactInboundShipment.import_job_id.is_distinct_from(int(import_job_id)),
                tuple_(
                    FactInboundShipment.report_type,
                    FactInboundShipment.order_no,
                    FactInboundShipment.order_line,
                    FactInboundShipment.item_code,
                ).in_(batch),
            )
        ).all()
        for rt, order, oline, item, ou, key in found:
            out[(str(rt), _norm(order), _norm(oline), _norm(item), _norm(ou))].add(str(key))
    return out


def _apply_closed_and_duplicate_guard(
    db: Session,
    *,
    tenant_id: str,
    import_job_id: int,
    lines: list[ShipmentEvidenceLine],
    values: list[dict[str, Any]],
    guard_report_types: frozenset[str],
    report: dict[str, Any],
) -> tuple[list[ShipmentEvidenceLine], list[dict[str, Any]]]:
    """Drop the rows an undated complete-book file must not write (GOV-008 M2).

    1. A row whose fact key is a closed fact is not written: a closed fact stays closed. Without a report date the
       file cannot say it is newer than the close.
    2. An open row whose order line is already open under another key (another job) is not written: both would be open
       for one line. The fact already open stays; a dated file re-keys it.
    Both are counted in ``report``; nothing is deleted and no fact is touched.
    """
    guarded = [i for i, v in enumerate(values) if v.get("report_type") in guard_report_types and v.get("fact_upsert_key")]
    closed_keys = _closed_keys_among(db, sorted({str(values[i]["fact_upsert_key"]) for i in guarded}))
    open_rows = [values[i] for i in guarded if (values[i].get("line_state") or "").strip().lower() != "shipped"]
    identities = _open_line_identities_under_other_keys(db, tenant_id, import_job_id, open_rows)

    drop: set[int] = set()
    for i in guarded:
        v = values[i]
        key = str(v["fact_upsert_key"])
        qty = float(v.get("quantity") or 0)
        if key in closed_keys:
            drop.add(i)
            report["already_closed_not_reopened"] += 1
            report["already_closed_not_reopened_units"] += qty
            continue
        if (v.get("line_state") or "").strip().lower() == "shipped":
            continue
        ident = (str(v["report_type"]), _norm(v.get("order_no")), _norm(v.get("order_line")), _norm(v.get("item_code")), _norm(v.get("operating_unit")))
        others = identities.get(ident, set()) - {key}
        if others and not (_blank(v.get("order_no")) or _blank(v.get("order_line")) or _blank(v.get("item_code"))):
            drop.add(i)
            report["already_open_not_duplicated"] += 1
            report["already_open_not_duplicated_units"] += qty
    if not drop:
        return lines, values
    return [l for i, l in enumerate(lines) if i not in drop], [v for i, v in enumerate(values) if i not in drop]


def upsert_inbound_shipment_facts_for_job(
    db: Session,
    import_job_id: int,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = _UPSERT_CHUNK_SIZE,
    guard_report_types: frozenset[str] | None = None,
    report: dict[str, Any] | None = None,
) -> int:
    """Insert/update ``fact_inbound_shipment`` for every evidence line on the job.

    Shipped rows replace by PO-inclusive ``fact_upsert_key`` (invoice lines within PO sum).
    keep per-job ``source_key`` upsert semantics.

    ``guard_report_types`` (an undated complete-book file, GOV-008 M2): rows of these report types never re-open a closed
    fact and never add a second open fact for a line already open under another key. ``report`` (optional) receives the
    counts: ``already_closed_not_reopened``, ``already_open_not_duplicated`` (rows) and their ``_units``.
    The returned number is the evidence rows written, so it excludes the rows the guard left out.
    """
    from app.models.ingestion import ImportJob

    started = time.perf_counter()
    job = db.get(ImportJob, int(import_job_id))
    tid = (getattr(job, "tenant_id", None) or "default").strip() or "default" if job else "default"
    lines = list(
        db.scalars(
            select(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.import_job_id == int(import_job_id))
            .order_by(ShipmentEvidenceLine.id)
        ).all()
    )
    tbl = FactInboundShipment.__table__
    n = 0
    # Rows that share a fact key (invoice lines of one delivery + item + PO) add up inside one chunk, and a later chunk
    # replaces the key. So lines of one key are never split across chunks: they are kept together, at the place the key
    # first appears, and a chunk ends only between keys.
    values = [_row_values_from_evidence(line, tenant_id=tid) for line in lines]
    if report is None:
        report = {}
    for k in ("already_closed_not_reopened", "already_closed_not_reopened_units", "already_open_not_duplicated", "already_open_not_duplicated_units"):
        report.setdefault(k, 0)
    if guard_report_types:
        lines, values = _apply_closed_and_duplicate_guard(
            db, tenant_id=tid, import_job_id=int(import_job_id), lines=lines, values=values,
            guard_report_types=guard_report_types, report=report,
        )
    total = len(lines)
    groups: dict[str, list[int]] = {}
    for i, v in enumerate(values):
        groups.setdefault(str(v.get("fact_upsert_key") or f"#{i}"), []).append(i)
    chunks: list[list[int]] = []
    for idxs in groups.values():
        if not chunks or len(chunks[-1]) + len(idxs) > chunk_size:
            chunks.append([])
        chunks[-1].extend(idxs)
    for idxs in chunks:
        _upsert_evidence_chunk(db, tbl, [lines[i] for i in idxs], [values[i] for i in idxs], tenant_id=tid)
        n += len(idxs)
        if on_progress is not None:
            on_progress(n, total)
    db.flush()
    orphans = retire_orphaned_open_rows(db, int(import_job_id))
    if orphans["superseded"] or orphans["disappeared"]:
        logger.info("shipment_stage job_id=%s orphaned_open_rows_retired=%s", int(import_job_id), orphans)
    twins = retire_po_less_twins_written_by_job(db, int(import_job_id))
    if twins["retired"] or twins["quantity_differs"]:
        logger.info(
            "shipment_stage job_id=%s po_less_twins_retired=%s repointed=%s quantity_differs=%s",
            int(import_job_id), twins["retired"], twins["repointed"], twins["quantity_differs"][:20],
        )
    logger.info(
        "shipment_stage job_id=%s stage=%s elapsed_s=%.3f",
        int(import_job_id),
        "upsert_inbound_shipment_facts",
        time.perf_counter() - started,
    )
    return n
