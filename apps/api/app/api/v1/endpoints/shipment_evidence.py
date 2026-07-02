"""Read APIs for canonical shipment / order evidence lines."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
    shipment_evidence_read_relation,
)
from app.core.feature_flags import shipment_bitemporal_read_enabled
from app.services.imports.import_background_slots import (
    SLOT_MAIN,
    SLOT_SHIPMENT_BULK,
    set_task_slot_on_job,
)
from app.services.imports.import_job_background_metadata import persist_pipeline_queued_at
from app.services.imports.shipment_bulk_steward_enqueue import (
    TASK_SHIPMENT_BULK_APPLY_PLANS,
    TASK_SHIPMENT_BULK_MAP_CUSTOMER,
    TASK_SHIPMENT_BULK_PROVISIONAL_CUSTOMERS,
    dev_shipment_bulk_task_results,
    enqueue_shipment_bulk_task,
    run_shipment_bulk_apply_plans_sync,
    run_shipment_bulk_map_customer_sync,
    run_shipment_bulk_provisional_customers_sync,
)
from app.services.imports.shipment_apply_sync import run_shipment_apply_sync
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)
from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    execute_clear_special_category_shipment_candidate,
    execute_create_provisional_shipment_customer,
    execute_create_provisional_shipment_distributor,
    execute_manual_special_category_shipment_candidate,
    execute_map_shipment_customer,
    execute_map_shipment_distributor,
    execute_reject_shipment_mapping_candidate,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


async def _unresolved_shipment_mapping_candidate_count(db: AsyncSession, job_id: int, entity_type: str) -> int:
    stmt = (
        select(func.count())
        .select_from(ImportEntityMappingCandidate)
        .where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.entity_type == entity_type,
            ImportEntityMappingCandidate.status == "needs_review",
        )
    )
    raw = await db.scalar(stmt)
    return int(raw or 0)


def _dispatch_shipment_apply(job_id: int) -> tuple[bool, str | None]:
    """Publish ``imports.shipment_apply`` to the broker via the shared dispatch helper."""
    from app.services.imports.import_dispatch import enqueue_import_worker_task

    return enqueue_import_worker_task(
        job_id,
        task_name="imports.shipment_apply",
        log_label="Shipment apply",
        in_process_thread_name=f"shipment-apply-{job_id}",
        sync_work=run_shipment_apply_sync,
    )


def _is_admin(x_user_role: str | None) -> bool:
    return (x_user_role or "").strip().lower() == "admin"


def _require_admin(x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None) -> None:
    if not _is_admin(x_user_role):
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Requires X-User-Role: admin"},
        )


def _line_to_dict(
    row: Any,
    *,
    product_sku: str | None,
    distributor_code: str | None,
    include_raw_row: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "import_job_id": row.import_job_id,
        "source_sheet": row.source_sheet,
        "source_row_number": row.source_row_number,
        "report_type": row.report_type,
        "line_state": row.line_state,
        "source_key": row.source_key,
        "operating_unit": row.operating_unit,
        "bill_to_raw": row.bill_to_raw,
        "ship_to_raw": row.ship_to_raw,
        "order_no": row.order_no,
        "customer_po": row.customer_po,
        "order_line": row.order_line,
        "delivery_no": row.delivery_no,
        "invoice_line": row.invoice_line,
        "item_code": row.item_code,
        "sales_model_name": row.sales_model_name,
        "customer_item": row.customer_item,
        "ean_code": row.ean_code,
        "upc_code": row.upc_code,
        "mpor_item_no": row.mpor_item_no,
        "quantity": float(row.quantity) if row.quantity is not None else None,
        "unit_price": float(row.unit_price) if row.unit_price is not None else None,
        "amount": float(row.amount) if row.amount is not None else None,
        "currency_code": row.currency_code,
        "ship_confirm_date": row.ship_confirm_date.isoformat() if row.ship_confirm_date else None,
        "schedule_ship_date": row.schedule_ship_date.isoformat() if row.schedule_ship_date else None,
        "promise_date": row.promise_date.isoformat() if row.promise_date else None,
        "exwork_date": row.exwork_date.isoformat() if row.exwork_date else None,
        "erd_date": row.erd_date.isoformat() if row.erd_date else None,
        "est_pod_date": row.est_pod_date.isoformat() if row.est_pod_date else None,
        "pod_date": row.pod_date.isoformat() if row.pod_date else None,
        "customer_dealer_token": row.customer_dealer_token,
        "customer_id": row.customer_id,
        "customer_resolution_status": row.customer_resolution_status,
        "product_id": row.product_id,
        "product_sku": product_sku,
        "product_resolution_status": row.product_resolution_status,
        "product_resolution_token": row.product_resolution_token,
        "product_resolution_detail": row.product_resolution_detail,
        "distributor_id": row.distributor_id,
        "distributor_code": distributor_code,
        "distributor_resolution_status": row.distributor_resolution_status,
        "distributor_resolution_token": row.distributor_resolution_token,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_raw_row:
        out["raw_source_row"] = row.raw_source_row
    return out


def _apply_filters(stmt: Any, model: Any, **kwargs: Any) -> Any:
    import_job_id = kwargs.get("import_job_id")
    line_state = kwargs.get("line_state")
    report_type = kwargs.get("report_type")
    product_resolution_status = kwargs.get("product_resolution_status")
    distributor_resolution_status = kwargs.get("distributor_resolution_status")
    search = kwargs.get("search")
    if import_job_id is not None:
        stmt = stmt.where(model.import_job_id == import_job_id)
    if line_state:
        stmt = stmt.where(model.line_state == line_state)
    if report_type:
        stmt = stmt.where(model.report_type == report_type)
    if product_resolution_status:
        stmt = stmt.where(model.product_resolution_status == product_resolution_status)
    if distributor_resolution_status:
        stmt = stmt.where(model.distributor_resolution_status == distributor_resolution_status)
    if search and str(search).strip():
        term = f"%{str(search).strip()}%"
        stmt = stmt.where(
            or_(
                model.bill_to_raw.ilike(term),
                model.ship_to_raw.ilike(term),
                model.customer_dealer_token.ilike(term),
                model.item_code.ilike(term),
                model.sales_model_name.ilike(term),
                model.order_no.ilike(term),
                model.delivery_no.ilike(term),
            )
        )
    return stmt


@router.get("/raw-column-keys")
async def list_shipment_evidence_raw_column_keys(
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    import_job_id: int = Query(..., ge=1),
) -> dict[str, Any]:
    """Distinct JSON keys present in ``raw_source_row`` for one import job (for admin column picker)."""
    _require_admin(x_user_role)
    relation = shipment_evidence_read_relation()
    superseded_clause = (
        "" if shipment_bitemporal_read_enabled() else " AND corpus_superseded_at IS NULL"
    )
    sql = text(
        f"""
        SELECT DISTINCT jsonb_object_keys(raw_source_row) AS k
        FROM {relation}
        WHERE import_job_id = :import_job_id{superseded_clause}
        ORDER BY 1
        """
    )
    res = await db.execute(sql, {"import_job_id": import_job_id})
    keys = [str(row[0]) for row in res.fetchall() if row[0] is not None]
    return {"import_job_id": import_job_id, "keys": keys}


@router.get("/import-jobs/{job_id}/mapping-candidates")
async def list_shipment_import_job_mapping_candidates(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> list[dict[str, Any]]:
    """``shipment_distributor`` and ``shipment_customer_token`` candidates for an inbound_shipments job."""
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    res = await db.execute(
        select(ImportEntityMappingCandidate)
        .where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.entity_type.in_(
                (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY)
            ),
        )
        .order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.normalized_key)
    )
    rows = res.scalars().all()
    sug_dist_ids = [int(r.suggested_entity_id) for r in rows if r.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY and r.suggested_entity_id]
    sug_cust_ids = [int(r.suggested_entity_id) for r in rows if r.entity_type == SHIPMENT_CUSTOMER_ENTITY and r.suggested_entity_id]
    dist_names: dict[int, dict[str, str]] = {}
    cust_names: dict[int, dict[str, str]] = {}
    if sug_dist_ids:
        dr = await db.execute(select(DimDistributor).where(DimDistributor.id.in_(sug_dist_ids)))
        for d in dr.scalars().all():
            dist_names[int(d.id)] = {"distributor_code": d.code or "", "distributor_name": d.name or ""}
    if sug_cust_ids:
        cr = await db.execute(select(DimCustomer).where(DimCustomer.id.in_(sug_cust_ids)))
        for c in cr.scalars().all():
            cust_names[int(c.id)] = {"customer_code": c.code or "", "customer_name": c.name or ""}
    out: list[dict[str, Any]] = []
    for r in rows:
        sid = int(r.suggested_entity_id) if r.suggested_entity_id is not None else None
        dh = dist_names.get(sid) if r.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY and sid is not None else None
        ch = cust_names.get(sid) if r.entity_type == SHIPMENT_CUSTOMER_ENTITY and sid is not None else None
        ctx = r.context if isinstance(r.context, dict) else {}
        out.append(
            {
                "id": r.id,
                "import_job_id": r.import_job_id,
                "source_definition_id": r.source_definition_id,
                "entity_type": r.entity_type,
                "normalized_key": r.normalized_key,
                "dealer_group_token": r.dealer_group_token,
                "row_count": r.row_count,
                "total_units": float(r.total_units) if r.total_units is not None else None,
                "total_reported_value": float(r.total_reported_value) if r.total_reported_value is not None else None,
                "sample_raw_values": r.sample_raw_values,
                "suggested_entity_id": r.suggested_entity_id,
                "suggested_distributor_code": dh["distributor_code"] if dh else None,
                "suggested_distributor_name": dh["distributor_name"] if dh else None,
                "suggested_customer_code": ch["customer_code"] if ch else None,
                "suggested_customer_name": ch["customer_name"] if ch else None,
                "suggested_action": ctx.get("suggested_action"),
                "match_reason": r.match_reason,
                "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
                "status": r.status,
                "context": r.context,
                "created_at": r.created_at.isoformat() if r.created_at is not None else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
            }
        )
    return out


@router.get("/import-jobs/{job_id}/mapping-candidates/paginated")
async def list_shipment_import_job_mapping_candidates_paginated(
    job_id: int,
    skip: int = 0,
    limit: int = 100,
    entity: str = "all",
    party: str = "all",
    verify_name_only: bool = False,
    special_category_only: bool = False,
    possible_duplicates_only: bool = False,
    duplicate_unresolved_only: bool = False,
    status: str = "open",
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Paginated shipment mapping candidates (default limit 100, max 1000)."""
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    from app.schemas.shipment_mapping_candidates import ShipmentMappingCandidatesListParams
    from app.services.imports.shipment_mapping_candidates_list import list_shipment_mapping_candidates_sync

    params = ShipmentMappingCandidatesListParams(
        skip=skip,
        limit=limit,
        entity=entity,  # type: ignore[arg-type]
        party=party,  # type: ignore[arg-type]
        verify_name_only=verify_name_only,
        special_category_only=special_category_only,
        possible_duplicates_only=possible_duplicates_only,
        duplicate_unresolved_only=duplicate_unresolved_only,
        status=status,  # type: ignore[arg-type]
    )

    def _work(sess: Session) -> dict[str, Any]:
        return list_shipment_mapping_candidates_sync(sess, job_id, params)

    from app.db.session_sync import SessionLocal

    with SessionLocal() as sess:
        return _work(sess)


@router.get("/import-jobs/{job_id}/mapping-candidates/tab-counts")
async def shipment_mapping_candidate_tab_counts(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    from app.services.imports.shipment_mapping_candidates_tab_counts import (
        shipment_mapping_candidate_tab_counts_sync,
    )

    def _work(sess: Session) -> dict[str, Any]:
        return shipment_mapping_candidate_tab_counts_sync(sess, job_id)

    from app.db.session_sync import SessionLocal

    with SessionLocal() as sess:
        return _work(sess)


class ShipmentResolutionPlanGenerateBody(BaseModel):
    candidate_ids: list[int] | None = None


class ShipmentResolutionPlanOverride(BaseModel):
    candidate_id: int
    suggested_action: str | None = None
    suggested_target_id: int | None = None
    hold_for_manual_review: bool | None = None
    confirm_previously_resolved: bool | None = None


class ShipmentResolutionPlanEffectiveBody(BaseModel):
    candidate_ids: list[int] | None = None
    overrides: list[ShipmentResolutionPlanOverride] = Field(default_factory=list)


class ShipmentResolutionPlanApplyBody(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)
    overrides: list[ShipmentResolutionPlanOverride] = Field(default_factory=list)


@router.post("/import-jobs/{job_id}/resolution-plan/compute-async", status_code=202)
async def shipment_resolution_plan_compute_async(
    job_id: int,
    body: ShipmentResolutionPlanGenerateBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        job = s.get(ImportJob, job_id)
        if not job or (job.template_slug or "") != "inbound_shipments":
            raise HTTPException(status_code=404, detail="Shipment import job not found")
    payload = {"candidate_ids": list(body.candidate_ids) if body.candidate_ids else None}
    from app.services.imports.shipment_bulk_steward_enqueue import (
        TASK_SHIPMENT_RESOLUTION_PLAN_COMPUTE,
        enqueue_shipment_bulk_task,
        run_shipment_resolution_plan_compute_sync,
    )

    task_id, async_poll = enqueue_shipment_bulk_task(
        task_name=TASK_SHIPMENT_RESOLUTION_PLAN_COMPUTE,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_shipment_resolution_plan_compute_sync(job_id, payload),
        dev_prefix="ship-plan-compute",
    )
    _write_shipment_bulk_slot(job_id, task_id, async_poll=async_poll, label="Computing resolution plan…")
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "async": True}


@router.post("/import-jobs/{job_id}/resolution-plan", status_code=200)
async def shipment_resolution_plan_generate(
    job_id: int,
    body: ShipmentResolutionPlanGenerateBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    from app.services.imports.shipment_resolution_plan import build_shipment_resolution_plan_sync

    def _work(sess: Session) -> dict[str, Any]:
        return build_shipment_resolution_plan_sync(sess, job_id, candidate_ids=body.candidate_ids)

    with SessionLocal() as sess:
        try:
            return _work(sess)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import-jobs/{job_id}/resolution-plan/effective", status_code=200)
async def shipment_resolution_plan_effective(
    job_id: int,
    body: ShipmentResolutionPlanEffectiveBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    from app.services.imports.shipment_resolution_plan import build_shipment_resolution_plan_effective_sync

    def _work(sess: Session) -> dict[str, Any]:
        return build_shipment_resolution_plan_effective_sync(
            sess,
            job_id,
            candidate_ids=body.candidate_ids,
            overrides=[o.model_dump(exclude_unset=True) for o in body.overrides],
        )

    with SessionLocal() as sess:
        try:
            return _work(sess)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import-jobs/{job_id}/resolution-plan/apply-async", status_code=202)
async def shipment_resolution_plan_apply_async(
    job_id: int,
    body: ShipmentResolutionPlanApplyBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        job = s.get(ImportJob, job_id)
        if not job or (job.template_slug or "") != "inbound_shipments":
            raise HTTPException(status_code=404, detail="Shipment import job not found")
    payload = {
        "candidate_ids": [int(x) for x in body.candidate_ids],
        "overrides": [o.model_dump(exclude_unset=True) for o in body.overrides],
    }
    from app.services.imports.shipment_bulk_steward_enqueue import (
        TASK_SHIPMENT_RESOLUTION_PLAN_APPLY,
        enqueue_shipment_bulk_task,
        run_shipment_resolution_plan_apply_sync,
    )

    task_id, async_poll = enqueue_shipment_bulk_task(
        task_name=TASK_SHIPMENT_RESOLUTION_PLAN_APPLY,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_shipment_resolution_plan_apply_sync(job_id, payload),
        dev_prefix="ship-plan-apply",
    )
    _write_shipment_bulk_slot(job_id, task_id, async_poll=async_poll, label="Applying resolution plan…")
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "async": True}


class ShipmentMapDistributorBody(BaseModel):
    distributor_id: int = Field(ge=1)
    raw_token: str | None = Field(default=None, max_length=512)


class ShipmentCreateProvisionalDistributorBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=256)
    distributor_code: str | None = Field(default=None, max_length=32)
    confirm_for_suspicious_token: bool = False


class ShipmentMapCustomerBody(BaseModel):
    customer_id: int = Field(ge=1)
    raw_token: str | None = Field(default=None, max_length=512)


class ShipmentCreateProvisionalCustomerBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=256)
    region_id: int | None = Field(default=None, ge=1)
    channel_id: int | None = Field(default=None, ge=1)
    preferred_distributor_id: int | None = Field(default=None, ge=1)
    partner_tier: str | None = Field(default="unmanaged", max_length=32)
    notes_summary: str | None = Field(default=None, max_length=512)


class ShipmentBulkProvisionalCustomersBody(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)
    display_names: dict[str, str] | None = Field(default=None)
    region_id: int | None = Field(default=None, ge=1)
    channel_id: int | None = Field(default=None, ge=1)
    preferred_distributor_id: int | None = Field(default=None, ge=1)
    partner_tier: str | None = Field(default="unmanaged", max_length=32)
    notes_summary: str | None = Field(default=None, max_length=512)


class ShipmentBulkMapCustomerBody(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)
    customer_id: int = Field(ge=1)


class ShipmentBulkApplyPlansBody(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)


def _write_shipment_bulk_slot(job_id: int, task_id: str, *, async_poll: bool, label: str) -> None:
    """Record the shipment bulk Celery task on the job so the activity feed shows it and
    cancel/retry clears it (registered slot ``shipment_bulk_task``)."""
    with SessionLocal() as meta_db:
        job = meta_db.get(ImportJob, job_id)
        if job is not None:
            set_task_slot_on_job(job, SLOT_SHIPMENT_BULK, task_id=task_id, async_poll=async_poll, label=label)
            meta_db.commit()


@router.post("/import-jobs/{job_id}/bulk-apply-confirmed-plans", status_code=202)
async def shipment_import_job_bulk_apply_confirmed_plans(
    job_id: int,
    body: ShipmentBulkApplyPlansBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Enqueue apply of each candidate's persisted planner ``suggested_action`` as a background task.

    Returns ``{async_poll, task_id}`` immediately; poll ``.../shipment-bulk-task/{task_id}``. Bypasses
    partner-text guards in the worker (existing plan executes). No proxy-timeout risk on large jobs.
    """
    _require_admin(x_user_role)
    with SessionLocal() as s:
        job = s.get(ImportJob, job_id)
        if not job or (job.template_slug or "") != "inbound_shipments":
            raise HTTPException(status_code=404, detail="Shipment import job not found")
    payload = {"candidate_ids": [int(x) for x in body.candidate_ids]}
    task_id, async_poll = enqueue_shipment_bulk_task(
        task_name=TASK_SHIPMENT_BULK_APPLY_PLANS,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_shipment_bulk_apply_plans_sync(job_id, payload),
        dev_prefix="ship-bulk-plans",
    )
    _write_shipment_bulk_slot(job_id, task_id, async_poll=async_poll, label="Applying confirmed plans…")
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "action": "bulk_apply_plans"}


@router.post("/import-candidates/bulk-map-customer", status_code=202)
async def shipment_import_candidates_bulk_map_customer(
    body: ShipmentBulkMapCustomerBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Enqueue bulk-map of many shipment customer candidates to one existing customer (background task).

    Returns ``{async_poll, task_id}`` immediately; poll ``.../shipment-bulk-task/{task_id}``.
    """
    _require_admin(x_user_role)
    job_id_for_slot: int | None = None
    with SessionLocal() as s:
        first = s.get(ImportEntityMappingCandidate, int(body.candidate_ids[0]))
        if first is not None and first.entity_type == SHIPMENT_CUSTOMER_ENTITY:
            job_id_for_slot = int(first.import_job_id)
    payload = {"candidate_ids": [int(x) for x in body.candidate_ids], "customer_id": int(body.customer_id)}
    task_id, async_poll = enqueue_shipment_bulk_task(
        task_name=TASK_SHIPMENT_BULK_MAP_CUSTOMER,
        job_id=job_id_for_slot or 0,
        payload=payload,
        run_sync=lambda: run_shipment_bulk_map_customer_sync(job_id_for_slot or 0, payload),
        dev_prefix="ship-bulk-map",
    )
    if job_id_for_slot is not None:
        _write_shipment_bulk_slot(job_id_for_slot, task_id, async_poll=async_poll, label="Mapping channel partners…")
    return {
        "import_job_id": job_id_for_slot,
        "task_id": task_id,
        "async_poll": async_poll,
        "action": "bulk_map_customer",
    }


@router.post("/import-candidates/{candidate_id}/map-distributor")
async def shipment_import_candidate_map_distributor(
    candidate_id: int,
    body: ShipmentMapDistributorBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
            raise HTTPException(status_code=404, detail="Shipment distributor candidate not found")
        try:
            return execute_map_shipment_distributor(
                s, cand, distributor_id=body.distributor_id, raw_token=body.raw_token
            )
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


@router.post("/import-candidates/{candidate_id}/create-provisional-distributor")
async def shipment_import_candidate_create_provisional_distributor(
    candidate_id: int,
    body: ShipmentCreateProvisionalDistributorBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
            raise HTTPException(status_code=404, detail="Shipment distributor candidate not found")
        try:
            return execute_create_provisional_shipment_distributor(
                s,
                cand,
                display_name=body.display_name,
                distributor_code=body.distributor_code,
                confirm_for_suspicious_token=body.confirm_for_suspicious_token,
            )
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


@router.post("/import-candidates/{candidate_id}/map-customer")
async def shipment_import_candidate_map_customer(
    candidate_id: int,
    body: ShipmentMapCustomerBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
            raise HTTPException(status_code=404, detail="Shipment customer candidate not found")
        try:
            return execute_map_shipment_customer(
                s, cand, customer_id=body.customer_id, raw_token=body.raw_token
            )
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


class ShipmentManualSpecialCategoryBody(BaseModel):
    special_category: Literal["noise_only", "internal_note"]


@router.post("/import-candidates/{candidate_id}/manual-special-category")
async def shipment_import_candidate_manual_special_category(
    candidate_id: int,
    body: ShipmentManualSpecialCategoryBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
            raise HTTPException(status_code=404, detail="Shipment mapping candidate not found")
        try:
            return execute_manual_special_category_shipment_candidate(
                s, cand, special_category=body.special_category
            )
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


@router.post("/import-candidates/{candidate_id}/clear-special-category")
async def shipment_import_candidate_clear_special_category(
    candidate_id: int,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
            raise HTTPException(status_code=404, detail="Shipment mapping candidate not found")
        try:
            return execute_clear_special_category_shipment_candidate(s, cand)
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


@router.post("/import-candidates/{candidate_id}/reject")
async def shipment_import_candidate_reject(
    candidate_id: int,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type not in (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY):
            raise HTTPException(status_code=404, detail="Shipment mapping candidate not found")
        try:
            return execute_reject_shipment_mapping_candidate(s, cand)
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


@router.post("/import-candidates/{candidate_id}/create-provisional-customer")
async def shipment_import_candidate_create_provisional_customer(
    candidate_id: int,
    body: ShipmentCreateProvisionalCustomerBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand or cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
            raise HTTPException(status_code=404, detail="Shipment customer candidate not found")
        try:
            return execute_create_provisional_shipment_customer(
                s,
                cand,
                display_name=body.display_name,
                region_id=body.region_id,
                channel_id=body.channel_id,
                preferred_distributor_id=body.preferred_distributor_id,
                partner_tier=body.partner_tier,
                notes_summary=body.notes_summary,
            )
        except ShipmentStewardOpError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail}) from exc


@router.post("/import-jobs/{job_id}/bulk-create-provisional-customers", status_code=202)
async def shipment_import_job_bulk_create_provisional_customers(
    job_id: int,
    body: ShipmentBulkProvisionalCustomersBody,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Enqueue bulk provisional customer creation as a background task (governance: steward-driven only).

    Returns ``{async_poll, task_id}`` immediately; poll ``.../shipment-bulk-task/{task_id}``. Provisional
    creation stays steward-initiated — this endpoint only backgrounds the work, it does not auto-create.
    """
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    payload: dict[str, Any] = {
        "candidate_ids": [int(x) for x in body.candidate_ids],
        "display_names": dict(body.display_names) if body.display_names else None,
        "region_id": body.region_id,
        "channel_id": body.channel_id,
        "preferred_distributor_id": body.preferred_distributor_id,
        "partner_tier": body.partner_tier,
        "notes_summary": body.notes_summary,
    }
    task_id, async_poll = enqueue_shipment_bulk_task(
        task_name=TASK_SHIPMENT_BULK_PROVISIONAL_CUSTOMERS,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_shipment_bulk_provisional_customers_sync(job_id, payload),
        dev_prefix="ship-bulk-prov",
    )
    _write_shipment_bulk_slot(job_id, task_id, async_poll=async_poll, label="Creating provisional customers…")
    return {
        "import_job_id": job_id,
        "task_id": task_id,
        "async_poll": async_poll,
        "action": "bulk_create_provisional_customers",
    }


@router.get("/import-jobs/{job_id}/shipment-bulk-task/{task_id}", status_code=200)
async def shipment_bulk_task_status(job_id: int, task_id: str) -> dict[str, Any]:
    """Poll a shipment bulk steward Celery task (or dev in-process / sync fallback) state + result.

    Mirrors ``mappings.dsi_steward_bulk_task_status``: clears the registered ``shipment_bulk_task``
    slot once the task is terminal so the activity feed does not keep showing a finished job.
    """
    dev_store = dev_shipment_bulk_task_results()
    dev_hit = dev_store.get(task_id)
    if dev_hit is not None:
        state = dev_hit.get("state", "SUCCESS")
        if state in ("SUCCESS", "FAILURE"):
            dev_store.pop(task_id, None)
        out: dict[str, Any] = {"import_job_id": job_id, "task_id": task_id, "state": state}
        if state == "SUCCESS":
            out["result"] = dev_hit.get("result")
        else:
            out["error"] = dev_hit.get("error")
        if state in ("SUCCESS", "FAILURE"):
            await asyncio.to_thread(_clear_shipment_bulk_slot, job_id)
        return out

    from celery.result import AsyncResult

    def _read() -> tuple[str, Any]:
        r = AsyncResult(task_id, app=celery_app)
        return r.state, r.info

    task_state, info = await asyncio.to_thread(_read)
    progress: dict[str, Any] = {"import_job_id": job_id, "task_id": task_id, "state": task_state}
    if task_state == "PROGRESS" and isinstance(info, dict):
        progress["phase"] = info.get("phase")
        progress["phase_label"] = info.get("phase_label")
        progress["current_row"] = info.get("current_row", 0)
        progress["total_rows"] = info.get("total_rows", 0)
        progress["pct"] = info.get("pct", 0)
    elif task_state == "SUCCESS":
        raw_result = await asyncio.to_thread(lambda: AsyncResult(task_id, app=celery_app).result)
        progress["result"] = raw_result if isinstance(raw_result, dict) else None
    elif task_state == "FAILURE":
        progress["error"] = str(info)[:800] if info is not None else "Task failed"

    if task_state in ("SUCCESS", "FAILURE", "REVOKED"):
        await asyncio.to_thread(_clear_shipment_bulk_slot, job_id)

    return progress


def _clear_shipment_bulk_slot(job_id: int) -> None:
    from app.services.imports.import_job_background_metadata import clear_background_task_metadata_on_job

    with SessionLocal() as sess:
        job = sess.get(ImportJob, job_id)
        if job and clear_background_task_metadata_on_job(job):
            sess.commit()


@router.post("/jobs/{job_id}/apply")
async def apply_shipment_import_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Apply an inbound_shipments import job in the background: auto-map ``map_*`` candidates, upsert facts, ``loaded``.

    Returns immediately. The work (auto-map → batched ``fact_inbound_shipment`` upsert → stage
    ``loaded``) runs in the Celery worker (or a dev in-process thread) with progress; poll
    ``/api/v1/imports/jobs/{job_id}/dsi-progress`` and the job stage. Re-applying a job already at
    ``loaded`` is an idempotent no-op that returns the current unresolved-candidate summary.
    """
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    if job.stage == STAGE_LOADED:
        unresolved_d = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_DISTRIBUTOR_ENTITY)
        unresolved_c = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_CUSTOMER_ENTITY)
        return {
            "async": False,
            "already_applied": True,
            "id": job.id,
            "status": job.status,
            "stage": job.stage,
            "template_slug": job.template_slug,
            "import_mode": job.import_mode,
            "unresolved_distributor_candidates": unresolved_d,
            "unresolved_customer_candidates": unresolved_c,
            "auto_applied_candidate_count": 0,
        }
    if job.stage != STAGE_VALIDATED:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_job_stage",
                "message": f"Job must be at stage {STAGE_VALIDATED!r} to apply; current stage is {job.stage!r}.",
            },
        )

    # Mark running + record dispatch time before handing off, so progress/background UI are accurate
    # the instant the request returns (mirrors the validate dispatch path).
    with SessionLocal() as sync_db:
        j = sync_db.get(ImportJob, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Shipment import job not found")
        j.import_mode = "apply"
        j.status = "running"
        persist_pipeline_queued_at(sync_db, j)
        sync_db.commit()

    dispatched, task_id = _dispatch_shipment_apply(job_id)

    if dispatched and task_id:
        with SessionLocal() as meta_db:
            j_meta = meta_db.get(ImportJob, job_id)
            if j_meta is not None:
                set_task_slot_on_job(j_meta, SLOT_MAIN, task_id=task_id)
                meta_db.commit()

    await db.refresh(job)

    if dispatched:
        return {
            "async": True,
            "id": job_id,
            "status": job.status,
            "stage": job.stage,
            "template_slug": job.template_slug,
            "import_mode": job.import_mode,
            "task_id": task_id,
            "message": "Apply started in the background worker.",
        }

    # Broker unavailable and no dev thread: apply ran inline and is already at ``loaded``.
    unresolved_d = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_DISTRIBUTOR_ENTITY)
    unresolved_c = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_CUSTOMER_ENTITY)
    return {
        "async": False,
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "template_slug": job.template_slug,
        "import_mode": job.import_mode,
        "unresolved_distributor_candidates": unresolved_d,
        "unresolved_customer_candidates": unresolved_c,
    }


@router.get("")
async def list_shipment_evidence(
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    import_job_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    search: str | None = None,
    include_raw_row: bool = Query(False),
) -> dict[str, Any]:
    _require_admin(x_user_role)
    EV = shipment_evidence_read_model()
    filt: dict[str, Any] = {
        "import_job_id": import_job_id,
        "line_state": line_state,
        "report_type": report_type,
        "product_resolution_status": product_resolution_status,
        "distributor_resolution_status": distributor_resolution_status,
        "search": search,
    }
    count_stmt = apply_active_evidence_filter(
        _apply_filters(select(func.count()).select_from(EV), EV, **filt),
        model=EV,
    )
    total = int((await db.execute(count_stmt)).scalar_one())

    q = apply_active_evidence_filter(
        _apply_filters(select(EV).order_by(EV.id.desc()), EV, **filt),
        model=EV,
    )
    res = await db.execute(q.offset(skip).limit(limit))
    rows = res.scalars().all()

    prod_ids = {r.product_id for r in rows if r.product_id}
    dist_ids = {r.distributor_id for r in rows if r.distributor_id}
    products: dict[int, str] = {}
    distributors: dict[int, str] = {}
    if prod_ids:
        pr = await db.execute(select(DimProduct).where(DimProduct.id.in_(prod_ids)))
        for p in pr.scalars().all():
            products[int(p.id)] = p.sku or ""
    if dist_ids:
        dr = await db.execute(select(DimDistributor).where(DimDistributor.id.in_(dist_ids)))
        for d in dr.scalars().all():
            distributors[int(d.id)] = d.code or d.name or ""

    items = [
        _line_to_dict(
            r,
            product_sku=products.get(int(r.product_id)) if r.product_id else None,
            distributor_code=distributors.get(int(r.distributor_id)) if r.distributor_id else None,
            include_raw_row=include_raw_row,
        )
        for r in rows
    ]
    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get("/change-events")
async def list_shipment_change_events(
    period: str | None = Query(None, description="Quarter filter e.g. 26Q2"),
    distributor_id: int | None = Query(None),
    operating_unit: str | None = Query(None),
    event_type: list[str] | None = Query(None, description="Filter: date_slip, qty_change, graduated, pod_reversal"),
    line_identity_key: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Derived-on-read shipment lifecycle events from observation chains (Plan D v1)."""
    _require_admin(x_user_role)
    from app.services.imports.shipment_change_events import (
        derive_change_events,
        group_events_by_line,
        summarize_change_events,
    )

    et_set = {t.strip().lower() for t in event_type} if event_type else None

    def _run() -> dict[str, Any]:
        with SessionLocal() as sync_db:
            events = derive_change_events(
                sync_db,
                period=period,
                distributor_id=distributor_id,
                operating_unit=operating_unit,
                event_types=et_set,
                line_identity_key=line_identity_key,
                limit=limit,
            )
            return {
                "summary": summarize_change_events(events),
                "total": len(events),
                "events": [e.to_dict() for e in events],
                "chains_by_line_identity_key": group_events_by_line(events),
            }

    return await asyncio.to_thread(_run)


@router.get("/{line_id}")
async def get_shipment_evidence_line(
    line_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    EV = shipment_evidence_read_model()
    row = await db.get(EV, line_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    job = await db.get(ImportJob, row.import_job_id)
    product_sku = None
    distributor_code = None
    if row.product_id:
        p = await db.get(DimProduct, row.product_id)
        product_sku = p.sku if p else None
    if row.distributor_id:
        d = await db.get(DimDistributor, row.distributor_id)
        distributor_code = (d.code or d.name) if d else None
    out = _line_to_dict(
        row,
        product_sku=product_sku,
        distributor_code=distributor_code,
        include_raw_row=True,
    )
    out["import_job_file_name"] = job.file_name if job else None
    out["import_job_status"] = job.status if job else None
    return out
