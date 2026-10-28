"""Close open-order facts that have left the latest shipment report.

An ACZA Shipped/Unshipped workbook is the whole open book at its report date.
Applying a newer report upserts the lines it still carries (stable ``source_key``)
and marks every other open fact in the same scope closed. Nothing is deleted.
The fact keeps the job that last carried the line. The closing job is recorded
on a new observation and on one ``platform_audit_event``.

``line_state`` is already ``varchar(32)``. ``closed_shipped`` and
``closed_disappeared`` fit, so this does not add a column.

A report dated before the newest applied report in the same scope writes no
facts and closes nothing, so a late load of an older file cannot reopen the book.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment
from app.models.ingestion import ImportJob
from app.models.platform_audit import PlatformAuditEvent
from app.services.imports.shipment_evidence_line_identity import (
    observation_payload_hash,
    stable_line_identity_key_from_fields,
)
from app.services.imports.shipment_evidence_observations import _observation_insert_statement
from app.services.imports.shipment_evidence_report_detect import (
    LINE_CLOSED_DISAPPEARED,
    LINE_CLOSED_SHIPPED,
    LINE_OPEN_ORDER,
    LINE_SHIPPED,
    CLOSED_LINE_STATES,
)
from app.services.imports.shipment_report_date import report_date_for_job
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

_OPEN_BOOK_ACTION = "open_book_close"


def exclude_closed_inbound(model):
    """SQLAlchemy predicate: the fact is still on the inbound book."""
    return func.lower(func.coalesce(model.line_state, "")).notin_(tuple(CLOSED_LINE_STATES))


def line_state_for_shipped_sheet(
    line_state: str | None,
    *,
    ship_confirm_date: date | None,
    report_date: date | None,
) -> str:
    """A Shipped-sheet row is open until its mapped ship-confirm date is on or before the report date.

    Unship and any other state are returned unchanged. The decision uses the mapped
    ``ship_confirm_date`` only. A missing report date cannot prove a confirm date
    is in the future, so a dated confirm stays shipped; a missing confirm is open.
    """
    state = (line_state or "").strip().lower()
    if state != LINE_SHIPPED:
        return line_state or ""
    confirm = _as_date(ship_confirm_date)
    if confirm is None:
        return LINE_OPEN_ORDER
    if report_date is not None and confirm > report_date:
        return LINE_OPEN_ORDER
    return LINE_SHIPPED


def job_is_older_than_applied_book(db: Session, job: ImportJob) -> bool:
    """True when this job's report date is strictly before the newest applied date in its scope."""
    mine = report_date_for_job(job)
    if mine is None:
        return False
    latest = _latest_other_report_date(db, job)
    return latest is not None and mine < latest


def write_shipment_facts_and_close_book(
    db: Session,
    job: ImportJob,
    *,
    on_progress=None,
) -> dict[str, Any]:
    """Upsert this job's facts, then close open facts the report no longer carries.

    An older report does neither. The caller commits.
    """
    if job_is_older_than_applied_book(db, job):
        logger.info(
            "shipment open book: job %s report date is older than the applied book; facts unchanged",
            job.id,
        )
        return {"fact_rows": 0, "closed": 0, "skipped_reason": "older_report_date"}

    from app.services.imports.shipment_inbound_facts import upsert_inbound_shipment_facts_for_job

    fact_rows = upsert_inbound_shipment_facts_for_job(db, int(job.id), on_progress=on_progress)
    closed = close_open_book_for_job(db, job)
    return {"fact_rows": fact_rows, "closed": len(closed), "skipped_reason": None}


def close_open_book_for_job(db: Session, job: ImportJob) -> list[dict[str, Any]]:
    """Close earlier open facts in each scope this job carries. No-op when this report is older or undated."""
    report_date = report_date_for_job(job)
    if report_date is None or job_is_older_than_applied_book(db, job):
        return []
    closed: list[dict[str, Any]] = []
    for scope in _scopes_for_job(db, int(job.id)):
        closed.extend(
            _close_scope(
                db,
                closing_job_id=int(job.id),
                tenant_id=scope["tenant_id"],
                report_type=scope["report_type"],
                operating_unit=scope["operating_unit"],
                report_date=report_date,
            )
        )
    if closed:
        _append_close_observations(db, closed, closing_job_id=int(job.id), report_date=report_date)
        _write_audit(db, tenant_id=str(getattr(job, "tenant_id", None) or "default"), job_id=int(job.id), closed=closed, report_date=report_date)
    return closed


def reclassify_unconfirmed_shipped(db: Session) -> list[int]:
    """Shipped facts with no ship-confirm date become open orders. Returns the fact ids."""
    rows = db.execute(
        text(
            """
            UPDATE fact_inbound_shipment
            SET line_state = 'open_order', updated_at = now()
            WHERE lower(line_state) = 'shipped'
              AND ship_confirm_date IS NULL
            RETURNING id
            """
        )
    ).all()
    return [int(row.id) for row in rows]


def close_against_newest_reports(db: Session, *, apply: bool = True) -> list[dict[str, Any]]:
    """Close open facts that are not on the newest dated report of their scope.

    Used by the one-off backfill. Each scope's closing job is that newest report.
    ``apply=False`` is a SELECT: it also lists shipped facts that have no confirm
    date, which the one-off reclassifies to open before it closes them.
    """
    closed: list[dict[str, Any]] = []
    for scope in _newest_scopes(db):
        job = db.get(ImportJob, int(scope["job_id"]))
        if job is None:
            continue
        report_date = scope["report_date"]
        batch = _close_scope(
            db,
            closing_job_id=int(job.id),
            tenant_id=scope["tenant_id"],
            report_type=scope["report_type"],
            operating_unit=scope["operating_unit"],
            report_date=report_date,
            include_unconfirmed_shipped=not apply,
            apply=apply,
        )
        if apply and batch:
            _append_close_observations(db, batch, closing_job_id=int(job.id), report_date=report_date)
        closed.extend(batch)
    return closed


def preview_unconfirmed_shipped_ids(db: Session) -> list[int]:
    rows = db.execute(
        text(
            """
            SELECT id
            FROM fact_inbound_shipment
            WHERE lower(line_state) = 'shipped'
              AND ship_confirm_date IS NULL
            ORDER BY id
            """
        )
    ).all()
    return [int(row.id) for row in rows]


def write_open_book_audit(
    db: Session,
    *,
    tenant_id: str,
    job_id: int,
    closed: list[dict[str, Any]],
    report_date: date,
    reclassified_ids: list[int] | None = None,
) -> None:
    """One platform audit event listing the facts a close touched."""
    _write_audit(
        db,
        tenant_id=tenant_id,
        job_id=job_id,
        closed=closed,
        report_date=report_date,
        reclassified_ids=reclassified_ids,
    )


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


# One YYYYMMDD token in the file name. Zero or two tokens → no report date.
_FILE_DATE_SQL = """
(
  SELECT CASE
    WHEN count(*) = 1
     AND (array_agg(token[1]))[1] ~ '^20[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])$'
    THEN to_date((array_agg(token[1]))[1], 'YYYYMMDD')
    ELSE NULL
  END
  FROM regexp_matches(j.file_name, '20[0-9]{6}', 'g') AS m(token)
)
"""


def _latest_other_report_date(db: Session, job: ImportJob) -> date | None:
    row = db.execute(
        text(
            f"""
            SELECT max({_FILE_DATE_SQL}) AS report_date
            FROM import_job j
            JOIN shipment_evidence_line l ON l.import_job_id = j.id
            WHERE j.status = 'completed'
              AND j.template_slug = 'inbound_shipments'
              AND j.id <> :job_id
              AND j.tenant_id = :tenant
              AND l.report_type IN (
                    SELECT DISTINCT report_type
                    FROM shipment_evidence_line
                    WHERE import_job_id = :job_id
                  )
            """
        ),
        {"job_id": int(job.id), "tenant": str(getattr(job, "tenant_id", None) or "default")},
    ).one()
    value = row.report_date
    return value if isinstance(value, date) else None


def _scopes_for_job(db: Session, job_id: int) -> list[dict[str, str]]:
    rows = db.execute(
        text(
            """
            SELECT DISTINCT j.tenant_id AS tenant_id,
                   l.report_type AS report_type,
                   coalesce(l.operating_unit, '') AS operating_unit
            FROM shipment_evidence_line l
            JOIN import_job j ON j.id = l.import_job_id
            WHERE l.import_job_id = :job_id
            """
        ),
        {"job_id": job_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def _newest_scopes(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            f"""
            WITH dated AS (
                SELECT j.id AS job_id,
                       j.tenant_id,
                       l.report_type,
                       coalesce(l.operating_unit, '') AS operating_unit,
                       {_FILE_DATE_SQL} AS report_date,
                       j.completed_at
                FROM shipment_evidence_line l
                JOIN import_job j ON j.id = l.import_job_id
                WHERE j.status = 'completed'
                  AND j.template_slug = 'inbound_shipments'
            ),
            known AS (
                SELECT * FROM dated WHERE report_date IS NOT NULL
            )
            SELECT DISTINCT ON (tenant_id, report_type, operating_unit)
                   job_id, tenant_id, report_type, operating_unit, report_date
            FROM known
            ORDER BY tenant_id, report_type, operating_unit,
                     report_date DESC, completed_at DESC NULLS LAST, job_id DESC
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


_CLASSIFY_SQL = """
CASE
    WHEN f.order_no IS NOT NULL
     AND f.item_code IS NOT NULL
     AND trim(f.order_no) <> ''
     AND trim(f.item_code) <> ''
     AND EXISTS (
        SELECT 1 FROM shipped_twin t
        WHERE t.ou_key = lower(trim(coalesce(f.operating_unit, '')))
          AND t.order_key = lower(trim(f.order_no))
          AND t.item_key = lower(trim(f.item_code))
     )
    THEN 'closed_shipped'
    ELSE 'closed_disappeared'
END
"""


def _close_scope(
    db: Session,
    *,
    closing_job_id: int,
    tenant_id: str,
    report_type: str,
    operating_unit: str,
    report_date: date,
    include_unconfirmed_shipped: bool = False,
    apply: bool = True,
) -> list[dict[str, Any]]:
    """Mark, or only list, open facts in this scope from an earlier or undated report.

    ``include_unconfirmed_shipped`` treats a shipped fact with no confirm date as still
    open. The one-off preview uses that before it reclassifies those rows. The update
    itself only touches ``open_order`` rows.
    """
    prefix = f"""
            WITH origin AS (
                SELECT j.id AS job_id, {_FILE_DATE_SQL} AS report_date
                FROM import_job j
            ),
            shipped_twin AS (
                SELECT lower(trim(coalesce(s.operating_unit, ''))) AS ou_key,
                       lower(trim(s.order_no)) AS order_key,
                       lower(trim(s.item_code)) AS item_key
                FROM fact_inbound_shipment s
                WHERE s.tenant_id = :tenant
                  AND lower(s.line_state) = 'shipped'
                  AND s.ship_confirm_date IS NOT NULL
                  AND s.ship_confirm_date <= :report_date
                  AND s.order_no IS NOT NULL
                  AND s.item_code IS NOT NULL
                  AND trim(s.order_no) <> ''
                  AND trim(s.item_code) <> ''
                GROUP BY 1, 2, 3
            ),
            doomed AS (
                SELECT f.id
                FROM fact_inbound_shipment f
                LEFT JOIN origin o ON o.job_id = f.import_job_id
                WHERE (
                    lower(f.line_state) = 'open_order'
                    OR (
                      CAST(:include_unconfirmed AS boolean)
                      AND lower(f.line_state) = 'shipped'
                      AND f.ship_confirm_date IS NULL
                    )
                )
                  AND f.tenant_id = :tenant
                  AND f.report_type = :report_type
                  AND coalesce(f.operating_unit, '') = :operating_unit
                  AND f.import_job_id IS DISTINCT FROM :closing_job_id
                  AND (o.report_date IS NULL OR o.report_date < :report_date)
            )
    """
    if apply:
        sql = prefix + f"""
            UPDATE fact_inbound_shipment f
            SET line_state = {_CLASSIFY_SQL},
                updated_at = now()
            FROM doomed
            WHERE f.id = doomed.id
              AND lower(f.line_state) = 'open_order'
            RETURNING f.id, f.line_state, f.quantity, f.order_no, f.item_code,
                      f.import_job_id AS origin_import_job_id, f.report_type, f.operating_unit,
                      f.tenant_id
        """
    else:
        sql = prefix + f"""
            SELECT f.id, {_CLASSIFY_SQL} AS line_state, f.quantity, f.order_no, f.item_code,
                   f.import_job_id AS origin_import_job_id, f.report_type, f.operating_unit,
                   f.tenant_id
            FROM fact_inbound_shipment f
            JOIN doomed ON doomed.id = f.id
        """
    rows = db.execute(
        text(sql),
        {
            "tenant": tenant_id,
            "report_type": report_type,
            "operating_unit": operating_unit,
            "closing_job_id": closing_job_id,
            "report_date": report_date,
            "include_unconfirmed": include_unconfirmed_shipped,
        },
    ).mappings().all()
    out = []
    for row in rows:
        item = dict(row)
        item["quantity"] = float(item["quantity"]) if item["quantity"] is not None else None
        item["closing_job_id"] = closing_job_id
        item["report_date"] = report_date.isoformat()
        out.append(item)
    return out


def _append_close_observations(
    db: Session,
    closed: list[dict[str, Any]],
    *,
    closing_job_id: int,
    report_date: date,
) -> None:
    # The UPDATE is raw SQL. Expire cached facts so the observation copies the closed state.
    db.expire_all()
    facts = {
        int(fact.id): fact
        for fact in db.scalars(
            select(FactInboundShipment).where(
                FactInboundShipment.id.in_([int(row["id"]) for row in closed])
            )
        ).all()
    }
    valid_from = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    observed_at = datetime.now(timezone.utc)
    values: list[dict[str, Any]] = []
    for row in closed:
        fact = facts.get(int(row["id"]))
        if fact is None:
            continue
        raw = dict(fact.raw_source_row) if isinstance(fact.raw_source_row, dict) else {}
        raw = to_jsonable(raw)
        raw["open_book_report_date"] = report_date.isoformat()
        raw["open_book_closed_by_job_id"] = closing_job_id
        payload = {
            "source_sheet": fact.source_sheet,
            "source_row_number": int(fact.source_row_number or 0),
            "report_type": fact.report_type,
            "line_state": fact.line_state,
            "source_key": f"closed:{int(fact.id)}",
            "operating_unit": fact.operating_unit,
            "bill_to_raw": fact.bill_to_raw,
            "ship_to_raw": fact.ship_to_raw,
            "order_no": fact.order_no,
            "customer_po": fact.customer_po,
            "purchase_order_id": fact.purchase_order_id,
            "order_line": fact.order_line,
            "delivery_no": fact.delivery_no,
            "invoice_line": fact.invoice_line,
            "item_code": fact.item_code,
            "sales_model_name": fact.sales_model_name,
            "customer_item": fact.customer_item,
            "ean_code": fact.ean_code,
            "upc_code": fact.upc_code,
            "mpor_item_no": fact.mpor_item_no,
            "quantity": float(fact.quantity) if fact.quantity is not None else None,
            "unit_price": float(fact.unit_price) if fact.unit_price is not None else None,
            "amount": float(fact.amount) if fact.amount is not None else None,
            "currency_code": fact.currency_code,
            "ship_confirm_date": fact.ship_confirm_date,
            "schedule_ship_date": fact.schedule_ship_date,
            "promise_date": fact.promise_date,
            "exwork_date": fact.exwork_date,
            "erd_date": fact.erd_date,
            "est_pod_date": fact.est_pod_date,
            "pod_date": fact.pod_date,
            "customer_dealer_token": fact.customer_dealer_token,
            "customer_id": fact.customer_id,
            "customer_resolution_status": fact.customer_resolution_status,
            "product_id": fact.product_id,
            "product_resolution_status": fact.product_resolution_status,
            "product_resolution_token": fact.product_resolution_token,
            "product_resolution_detail": fact.product_resolution_detail,
            "distributor_id": fact.distributor_id,
            "distributor_resolution_status": fact.distributor_resolution_status,
            "distributor_resolution_token": fact.distributor_resolution_token,
        }
        payload["line_identity_key"] = stable_line_identity_key_from_fields(
            line_state=LINE_OPEN_ORDER,
            operating_unit=fact.operating_unit,
            order_no=fact.order_no,
            order_line=fact.order_line,
            delivery_no=fact.delivery_no,
            invoice_line=fact.invoice_line,
            item_code=fact.item_code,
            purchase_order_id=fact.purchase_order_id,
            raw_source_row=raw,
        )
        payload["raw_source_row"] = raw
        payload["import_job_id"] = closing_job_id
        payload["evidence_line_id"] = None
        payload["valid_from"] = valid_from
        payload["observed_at"] = observed_at
        payload["source_row_hash"] = observation_payload_hash(payload)
        values.append(payload)
    for start in range(0, len(values), 500):
        db.execute(_observation_insert_statement(values[start : start + 500]))


def _write_audit(
    db: Session,
    *,
    tenant_id: str,
    job_id: int,
    closed: list[dict[str, Any]],
    report_date: date,
    reclassified_ids: list[int] | None = None,
) -> None:
    listed = [
        {
            "fact_id": int(row["id"]),
            "line_state": row["line_state"],
            "quantity": row["quantity"],
            "order_no": row["order_no"],
            "item_code": row["item_code"],
            "origin_import_job_id": row["origin_import_job_id"],
            "report_type": row["report_type"],
        }
        for row in closed
    ]
    db.add(
        PlatformAuditEvent(
            tenant_id=tenant_id or "default",
            actor="open-book",
            area="admin",
            action=_OPEN_BOOK_ACTION,
            target_type="import_job",
            target_id=str(job_id),
            detail_json={
                "report_date": report_date.isoformat(),
                "reclassified_unconfirmed_shipped": list(reclassified_ids or []),
                "closed_count": len(listed),
                "closed_shipped": sum(1 for row in listed if row["line_state"] == LINE_CLOSED_SHIPPED),
                "closed_disappeared": sum(1 for row in listed if row["line_state"] == LINE_CLOSED_DISAPPEARED),
                "facts": listed,
            },
        )
    )
    db.flush()
    db.flush()
