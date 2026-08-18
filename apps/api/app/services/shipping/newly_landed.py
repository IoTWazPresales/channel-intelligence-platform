"""SH-04 newly POD'd since prior report — consecutive observation LAG on pod_date.

Not ``landed_week`` (fact-level ISO week). Owner: ``GET /shipping/newly-landed``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import ImportJob
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.shipping.observation_transitions import (
    LINE_COLUMN_KEYS,
    attach_fact_line_columns,
    fact_evidence_scope_stmt,
    identity_scope_for_job,
    identity_scope_from_fact_subquery,
    observation_lag_window,
    _iso,
    _merge_line_columns,
    _qty,
)

INBOUND_TEMPLATE = "inbound_shipments"
_LOADED_STATUSES = ("completed", "loaded")


async def import_jobs_unusable_date_snapshots(
    db: AsyncSession, identity_keys: Select[Any]
) -> list[int]:
    """Jobs in this identity history with no ``pod_date`` and no ``est_pod_date``.

    Job 605 stored empty ``field_mapping``: 0 POD, 0 Est POD, but leftover Promise
    dates. Consecutive ETA LAG vs those promises looked like the whole file moved.
    Skip the snapshot so the prior report is the last job that captured POD/Est POD.
    """
    stmt = (
        select(ShipmentEvidenceObservation.import_job_id)
        .where(ShipmentEvidenceObservation.line_identity_key.in_(identity_keys))
        .group_by(ShipmentEvidenceObservation.import_job_id)
        .having(
            (func.count(ShipmentEvidenceObservation.pod_date) == 0)
            & (func.count(ShipmentEvidenceObservation.est_pod_date) == 0)
        )
    )
    return [int(x) for x in (await db.execute(stmt)).scalars().all() if x is not None]


async def import_jobs_with_zero_pod(
    db: AsyncSession, identity_keys: Select[Any]
) -> list[int]:
    """Inbound jobs in this identity history that recorded no ``pod_date`` at all."""
    stmt = (
        select(ShipmentEvidenceObservation.import_job_id)
        .where(ShipmentEvidenceObservation.line_identity_key.in_(identity_keys))
        .group_by(ShipmentEvidenceObservation.import_job_id)
        .having(func.count(ShipmentEvidenceObservation.pod_date) == 0)
    )
    return [int(x) for x in (await db.execute(stmt)).scalars().all() if x is not None]


def empty_newly_landed_result(*, source_job_id: int | None = None) -> dict[str, Any]:
    return {
        "count": 0,
        "rows": [],
        "source_job_id": source_job_id,
        "cohort_definition": "newly_landed_vs_prior_observation",
        "line_columns": sorted(LINE_COLUMN_KEYS),
        "skipped_unusable_job_ids": [],
    }


async def latest_inbound_shipment_job_id(db: AsyncSession) -> int | None:
    stmt = (
        select(ImportJob.id)
        .where(
            ImportJob.template_slug == INBOUND_TEMPLATE,
            ImportJob.status.in_(_LOADED_STATUSES),
        )
        .order_by(ImportJob.id.desc())
        .limit(1)
    )
    raw = await db.scalar(stmt)
    return int(raw) if raw is not None else None


async def newly_landed_transitions(
    db: AsyncSession,
    *,
    import_job_id: int | None = None,
    scoped_ids: list[int] | None = None,
    with_line_columns: bool = True,
    today=None,
) -> dict[str, Any]:
    """Rows where prior observation ``pod_date`` is null and current is set.

    Identity scope is the requested job (default: latest inbound apply) or the
    evidence lines of ``scoped_ids`` facts. Never current-incoming — those facts
    are unlanded by definition.
    """
    del today  # reserved for filter-parity callers; scoping is job/fact ids
    source_job_id = int(import_job_id) if import_job_id is not None else None
    if scoped_ids is not None:
        if not scoped_ids:
            return empty_newly_landed_result(source_job_id=source_job_id)
        fact_scope = fact_evidence_scope_stmt(
            today=date.today(),
            require_current_incoming=False,
            scoped_ids=scoped_ids,
        ).subquery()
        evid_ids, identity_keys = identity_scope_from_fact_subquery(fact_scope)
    else:
        if source_job_id is None:
            source_job_id = await latest_inbound_shipment_job_id(db)
        if source_job_id is None:
            return empty_newly_landed_result(source_job_id=None)
        evid_ids, identity_keys = identity_scope_for_job(source_job_id)

    zero_pod_jobs = await import_jobs_with_zero_pod(db, identity_keys)
    skip_ids = [jid for jid in zero_pod_jobs if source_job_id is None or jid != int(source_job_id)]
    line_win = observation_lag_window(
        identity_keys,
        {"pod_date": ShipmentEvidenceObservation.pod_date},
        exclude_import_job_ids=skip_ids,
    )
    stmt = (
        select(
            line_win.c.source_key,
            line_win.c.import_job_id,
            line_win.c.sales_model_name,
            line_win.c.quantity,
            line_win.c.bill_to_raw,
            line_win.c.customer_dealer_token,
            line_win.c.pod_date.label("current_pod"),
            line_win.c.prev_pod_date.label("previous_pod"),
        )
        .select_from(line_win)
        .where(
            line_win.c.prev_id.is_not(None),
            line_win.c.prev_pod_date.is_(None),
            line_win.c.pod_date.is_not(None),
            line_win.c.evidence_line_id.in_(evid_ids),
        )
        .order_by(line_win.c.pod_date.asc(), line_win.c.source_key.asc())
    )
    raw_rows = (await db.execute(stmt)).mappings().all()
    count = len(raw_rows)
    rows: list[dict[str, Any]] = []
    fact_cols: dict[str, dict[str, Any]] = {}
    if with_line_columns and raw_rows:
        fact_cols = await attach_fact_line_columns(
            db, [str(r["source_key"]) for r in raw_rows if r.get("source_key")]
        )
    for r in raw_rows:
        item: dict[str, Any] = {
            "source_key": r.get("source_key"),
            "import_job_id": int(r["import_job_id"]) if r.get("import_job_id") is not None else None,
            "previous_pod": _iso(r.get("previous_pod")),
            "current_pod": _iso(r.get("current_pod")),
        }
        if with_line_columns:
            _merge_line_columns(
                item,
                fact_cols=fact_cols,
                source_key=item.get("source_key"),
                date_value=r.get("current_pod"),
                fallback_sales_model=r.get("sales_model_name"),
                fallback_qty=r.get("quantity"),
                fallback_customer_token=r.get("customer_dealer_token"),
                fallback_bill_to=r.get("bill_to_raw"),
            )
        else:
            item["sales_model"] = r.get("sales_model_name")
            item["qty"] = _qty(r.get("quantity"))
            item["date"] = _iso(r.get("current_pod"))
        rows.append(item)
    return {
        "count": count,
        "rows": rows,
        "source_job_id": source_job_id,
        "cohort_definition": "newly_landed_vs_prior_observation",
        "line_columns": sorted(LINE_COLUMN_KEYS),
        "skipped_unusable_job_ids": skip_ids,
    }
