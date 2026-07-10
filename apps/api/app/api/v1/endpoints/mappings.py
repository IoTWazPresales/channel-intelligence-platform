import asyncio
import logging
import threading
import uuid
from typing import Any, Literal

from typing_extensions import Self

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session_sync import SessionLocal
from app.worker.celery_app import celery_app
from app.ingestion.pipeline import process_import_job_sync
from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob
from app.models.mapping import EntityMappingQueue
from app.schemas.dsi_resolution_plan_requests import (
    DsiResolutionPlanApplyBody,
    DsiResolutionPlanEffectiveBody,
    DsiResolutionPlanGenerateBody,
    DsiResolutionPlanRowOverrideBody,
)
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.import_background_slots import (
    KIND_DSI_BULK_IGNORE,
    KIND_DSI_RESOLUTION_PLAN_COMPUTE,
    SLOT_DSI_BULK,
    set_task_slot_on_job,
)
from app.services.imports.dsi_apply_completion import DsiApplyCompletionError, complete_dsi_import_job_to_loaded
from app.services.imports.dsi_resolution_plan import (
    build_dsi_resolution_plan_effective_sync,
    build_dsi_resolution_plan_sync,
    collect_dsi_job_unresolved_geo_tokens_sync,
    derive_effective_provisional_customer_geo_sync,
)
from app.services.imports.dsi_steward_geo_catalog import (
    create_channel_source_token_alias_sync,
    create_dim_channel_with_source_alias_sync,
    create_dim_region_with_source_alias_sync,
    register_region_from_geographic_hint_sync,
    suggest_geo_create_prefill_sync,
    create_region_source_token_alias_sync,
)
from app.services.imports.dsi_bulk_provisional_customers_sync import run_dsi_bulk_provisional_customers_sync
from app.services.imports.dsi_bulk_ignore_sync import run_dsi_bulk_ignore_sync
from app.services.imports.dsi_resolution_plan_apply_sync import run_dsi_resolution_plan_apply_sync
from app.services.imports.dsi_steward_task_dispatch import (
    assert_dsi_steward_background_dispatch_allowed,
    reusable_dsi_bulk_task_id,
)
from app.services.imports.dsi_steward_candidate_ops import (
    StewardOpError,
    _first_sample_raw,
    _source_customer_alias_raw_for_dsi_candidate,
    dsi_customer_alias_normalized_token,
    execute_create_provisional_dsi_customer,
    execute_create_provisional_dsi_distributor,
    execute_ignore_dsi_candidate,
    execute_acknowledge_dsi_duplicate_different_entity,
    execute_dsi_duplicate_same_entity,
    execute_dsi_duplicate_cluster_same_entity,
    execute_map_dsi_customer,
    execute_map_dsi_distributor,
    execute_resolve_dsi_product,
    preview_create_provisional_dsi_customer,
    preview_create_provisional_dsi_distributor,
    preview_ignore_dsi_candidate,
    preview_map_dsi_customer,
    preview_map_dsi_distributor,
    preview_resolve_dsi_product,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Dev-only in-process DSI bulk steward task results (shared with post-validate enqueue).
from app.services.imports import dsi_resolution_plan_enqueue as _dsi_plan_enqueue

_dev_dsi_bulk_task_results = _dsi_plan_enqueue._dev_dsi_bulk_task_results
_dev_dsi_bulk_provisional_results = _dev_dsi_bulk_task_results


def _require_admin_role(x_user_role: str | None = Header(default=None, alias="X-User-Role")) -> None:
    if (x_user_role or "").strip().lower() != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Admin maintenance requires X-User-Role: admin"},
        )


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/queue")
async def mapping_queue(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(EntityMappingQueue).order_by(EntityMappingQueue.id.desc()))
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "entity_type": r.entity_type,
            "raw_value": r.raw_value,
            "normalized_value": r.normalized_value,
            "suggested_entity_id": r.suggested_entity_id,
            "match_method": r.match_method,
            "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
            "status": r.status,
            "job_id": r.job_id,
            "context": r.context,
        }
        for r in rows
    ]


@router.post("/queue/{item_id}/approve")
async def approve(
    item_id: int, entity_id: int = Query(...), db: AsyncSession = Depends(get_db)
):
    item = await db.get(EntityMappingQueue, item_id)
    if not item:
        return {"ok": False}
    item.status = "approved"
    item.suggested_entity_id = entity_id
    item.match_method = "manual"
    await db.commit()
    return {"ok": True, "id": item_id}


@router.post("/queue/{item_id}/reject")
async def reject(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(EntityMappingQueue, item_id)
    if not item:
        return {"ok": False}
    item.status = "rejected"
    await db.commit()
    return {"ok": True, "id": item_id}


@router.delete("/queue/{item_id}", status_code=204)
async def delete_queue_item(item_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(EntityMappingQueue, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/queue/clear-all", status_code=200)
async def clear_mapping_queue(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(EntityMappingQueue))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.get("/import-jobs/{job_id}/distributor-si-candidates")
async def list_distributor_si_mapping_candidates(
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
):
    """Paginated aggregated DSI mapping candidates for an import job (default limit 100, max 1000)."""
    from app.schemas.dsi_mapping_candidates import DsiMappingCandidatesListParams
    from app.services.imports.dsi_mapping_candidates_list import list_dsi_mapping_candidates_sync

    params = DsiMappingCandidatesListParams(
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

    def _work(sess: Session) -> dict:
        return list_dsi_mapping_candidates_sync(sess, job_id, params)

    return await db.run_sync(_work)


@router.get("/import-jobs/{job_id}/distributor-si-candidates/tab-counts")
async def distributor_si_mapping_candidate_tab_counts(job_id: int, db: AsyncSession = Depends(get_db)):
    """Aggregated open / needs_review counts per entity tab (one query — not six paginated COUNT calls)."""
    from app.services.imports.dsi_mapping_candidates_tab_counts import dsi_mapping_candidate_tab_counts_sync

    def _work(sess: Session) -> dict:
        return dsi_mapping_candidate_tab_counts_sync(sess, job_id)

    return await db.run_sync(_work)


def _blank_customer_normalized_key(norm: str) -> bool:
    t = (norm or "").strip().lower()
    return t in ("", "__blank__", "none", "n/a", "na", "unknown")


async def _open_channel_customer_id(db: AsyncSession) -> int:
    r = await db.execute(select(DimCustomer.id).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
    cid = r.scalar_one_or_none()
    if cid is None:
        raise HTTPException(
            status_code=409,
            detail="Open Channel customer row is missing; run system reference bootstrap before using Open Channel mapping.",
        )
    return int(cid)


async def _get_dsi_candidate_or_404(candidate_id: int, db: AsyncSession) -> ImportEntityMappingCandidate:
    row = await db.get(ImportEntityMappingCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row


async def _bulk_effective_provisional_geo(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    fallback_region_id: int | None,
    fallback_channel_id: int | None,
    *,
    import_job_id: int,
) -> tuple[int | None, int | None]:
    """Merge per-candidate DSI source region/channel evidence with optional batch fallback IDs."""

    def work(sess: Session) -> tuple[int | None, int | None]:
        job = sess.get(ImportJob, import_job_id)
        g = derive_effective_provisional_customer_geo_sync(
            sess,
            cand,
            default_region_id=fallback_region_id,
            default_channel_id=fallback_channel_id,
            import_job=job,
        )
        er = g.get("effective_region_id")
        ec = g.get("effective_channel_id")
        return int(er) if er is not None else None, int(ec) if ec is not None else None

    return await db.run_sync(work)


class MapCustomerBody(BaseModel):
    customer_id: int = Field(..., ge=1)
    raw_token: str | None = Field(default=None, max_length=512)


class CreateProvisionalCustomerBody(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)
    region_id: int | None = Field(default=None, ge=1)
    channel_id: int | None = Field(default=None, ge=1)
    preferred_distributor_id: int | None = None
    partner_tier: str | None = Field(default="unmanaged", max_length=32)
    notes_summary: str | None = Field(default=None, max_length=512)


class MarkOpenChannelBody(BaseModel):
    """Assign Open Channel dim_customer via alias. Named dealers require explicit confirmation."""

    confirm_for_named_dealer: bool = False
    confirm_for_strategic_channel_hint: bool = False


class IgnoreCandidateBody(BaseModel):
    notes: str | None = None
    reason_code: str | None = Field(
        default=None,
        description="DSI product ignore reason: ignore_sku_indeterminate | ignore_no_catalogue",
    )


class MapDistributorBody(BaseModel):
    distributor_id: int = Field(..., ge=1)
    raw_token: str | None = Field(default=None, max_length=512)


class CreateProvisionalDistributorBody(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)
    distributor_code: str | None = Field(default=None, max_length=32)
    confirm_for_suspicious_token: bool = False


class ResolveProductCandidateBody(BaseModel):
    """Steward: bind a DSI ``product_identifier`` candidate to an existing Product Master row via ``ProductAlias``."""

    product_id: int = Field(..., ge=1)
    raw_token: str | None = Field(default=None, max_length=256)
    confirm_ineligible_product: bool = False
    audit_note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=128)


@router.post("/import-candidates/{candidate_id}/resolve-product", status_code=200)
async def resolve_dsi_product_candidate(
    candidate_id: int, body: ResolveProductCandidateBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_resolve_dsi_product(
            db,
            cand,
            product_id=body.product_id,
            raw_token=body.raw_token,
            confirm_ineligible_product=body.confirm_ineligible_product,
            audit_note=body.audit_note,
            idempotency_key=body.idempotency_key,
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-candidates/{candidate_id}/map-customer", status_code=200)
async def map_dsi_candidate_to_customer(
    candidate_id: int, body: MapCustomerBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_map_dsi_customer(
            db, cand, customer_id=body.customer_id, raw_token=body.raw_token
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


class DsiDuplicateReviewPeerBody(BaseModel):
    peer_normalized_key: str = Field(..., min_length=1, max_length=512)
    audit_note: str | None = Field(default=None, max_length=2000)


class DsiDuplicateSameEntityBody(DsiDuplicateReviewPeerBody):
    customer_id: int | None = Field(default=None, ge=1)
    display_name: str | None = Field(default=None, max_length=256)
    plan_suggested_target_id: int | None = Field(default=None, ge=1)
    raw_token: str | None = Field(default=None, max_length=512)


class DsiDuplicateClusterSameEntityBody(BaseModel):
    normalized_keys: list[str] = Field(..., min_length=2, max_length=32)
    customer_id: int | None = Field(default=None, ge=1)
    display_name: str | None = Field(default=None, max_length=256)
    plan_suggested_target_id: int | None = Field(default=None, ge=1)
    audit_note: str | None = Field(default=None, max_length=2000)


@router.post("/import-candidates/{candidate_id}/duplicate-review/different-entity", status_code=200)
async def acknowledge_dsi_duplicate_different_entity(
    candidate_id: int, body: DsiDuplicateReviewPeerBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_acknowledge_dsi_duplicate_different_entity(
            db,
            cand,
            peer_normalized_key=body.peer_normalized_key,
            audit_note=body.audit_note,
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-candidates/{candidate_id}/duplicate-review/same-entity", status_code=200)
async def resolve_dsi_duplicate_same_entity(
    candidate_id: int, body: DsiDuplicateSameEntityBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_dsi_duplicate_same_entity(
            db,
            cand,
            peer_normalized_key=body.peer_normalized_key,
            customer_id=body.customer_id,
            display_name=body.display_name,
            plan_suggested_target_id=body.plan_suggested_target_id,
            raw_token=body.raw_token,
            audit_note=body.audit_note,
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-jobs/{job_id}/duplicate-review/cluster-same-entity", status_code=200)
async def resolve_dsi_duplicate_cluster_same_entity(
    job_id: int, body: DsiDuplicateClusterSameEntityBody, db: AsyncSession = Depends(get_db)
):
    try:
        return await execute_dsi_duplicate_cluster_same_entity(
            db,
            job_id,
            normalized_keys=body.normalized_keys,
            customer_id=body.customer_id,
            display_name=body.display_name,
            plan_suggested_target_id=body.plan_suggested_target_id,
            audit_note=body.audit_note,
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-candidates/{candidate_id}/create-provisional-customer", status_code=200)
async def create_provisional_customer_from_dsi_candidate(
    candidate_id: int, body: CreateProvisionalCustomerBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)

    def _geo(sess: Session) -> dict[str, Any]:
        jid = cand.import_job_id
        job = sess.get(ImportJob, int(jid)) if jid is not None else None
        return derive_effective_provisional_customer_geo_sync(
            sess,
            cand,
            default_region_id=None,
            default_channel_id=None,
            import_job=job,
        )

    try:
        g = await db.run_sync(_geo)
        er = int(body.region_id) if body.region_id is not None else g.get("effective_region_id")
        ec = int(body.channel_id) if body.channel_id is not None else g.get("effective_channel_id")
        return await execute_create_provisional_dsi_customer(
            db,
            cand,
            display_name_override=body.display_name,
            region_id=int(er) if er is not None else None,
            channel_id=int(ec) if ec is not None else None,
            preferred_distributor_id=body.preferred_distributor_id,
            partner_tier=body.partner_tier,
            notes_summary=body.notes_summary,
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-candidates/{candidate_id}/mark-open-channel", status_code=200)
async def mark_dsi_candidate_open_channel(
    candidate_id: int, body: MarkOpenChannelBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    if cand.entity_type != "customer_dealer_token":
        raise HTTPException(status_code=400, detail="Candidate entity_type is not customer_dealer_token")
    ctx = cand.context if isinstance(cand.context, dict) else {}
    if ctx.get("strategic_channel_hint") and not body.confirm_for_strategic_channel_hint:
        raise HTTPException(
            status_code=400,
            detail="Channel evidence looks like a strategic marketplace or major retail chain; confirm_for_strategic_channel_hint=true to assign Open Channel, or map/create a customer instead.",
        )
    if not _blank_customer_normalized_key(cand.normalized_key) and not body.confirm_for_named_dealer:
        raise HTTPException(
            status_code=400,
            detail="Open Channel mapping for named dealer tokens requires confirm_for_named_dealer=true (or map/create a customer).",
        )
    oc_id = await _open_channel_customer_id(db)
    raw = _source_customer_alias_raw_for_dsi_candidate(cand)
    if not raw:
        raw = cand.normalized_key or "open-channel"
    # Key the alias on the candidate resolution identity (dealer-group primary) so future
    # rows for this token resolve to Open Channel — matches the customer resolver lookup.
    nt = dsi_customer_alias_normalized_token(cand)
    if not nt:
        nt = "open-channel-token"
    alias = CustomerSourceTokenAlias(
        customer_id=oc_id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        status="approved",
        notes=f"Steward marked Open Channel from candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    db.add(alias)
    try:
        cand.status = "waived_open_channel"
        cand.suggested_entity_id = oc_id
        cand.match_reason = "steward_open_channel_alias"
        await db.commit()
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create alias")
    return {"ok": True, "alias_id": alias.id, "open_channel_customer_id": oc_id, "candidate_id": cand.id}


@router.post("/import-candidates/{candidate_id}/ignore", status_code=200)
async def ignore_dsi_candidate(candidate_id: int, body: IgnoreCandidateBody, db: AsyncSession = Depends(get_db)):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_ignore_dsi_candidate(db, cand, notes=body.notes, reason_code=body.reason_code)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-candidates/{candidate_id}/map-distributor", status_code=200)
async def map_dsi_candidate_to_distributor(
    candidate_id: int, body: MapDistributorBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_map_dsi_distributor(
            db, cand, distributor_id=body.distributor_id, raw_token=body.raw_token
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/import-candidates/{candidate_id}/create-provisional-distributor", status_code=200)
async def create_provisional_distributor_from_dsi_candidate(
    candidate_id: int, body: CreateProvisionalDistributorBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    try:
        return await execute_create_provisional_dsi_distributor(
            db,
            cand,
            display_name_override=body.display_name,
            distributor_code_override=body.distributor_code,
            confirm_for_suspicious_token=body.confirm_for_suspicious_token,
        )
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def _assert_dsi_import_job(db: AsyncSession, job_id: int) -> ImportJob:
    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    if (job.template_slug or "") != "distributor_inventory":
        raise HTTPException(status_code=400, detail="Job is not a distributor sales & inventory import")
    return job


DSI_BULK_STEWARD_MAX_CANDIDATE_IDS = 200
DSI_BULK_STEWARD_MAX_IGNORE_CANDIDATE_IDS = 1000


class DsiBulkStewardBody(BaseModel):
    """Bulk steward preview/apply: same validation rules as single-row endpoints."""

    action: Literal[
        "ignore",
        "map_customer",
        "map_distributor",
        "resolve_product",
        "create_provisional_customer",
        "create_provisional_distributor",
    ]
    candidate_ids: list[int] = Field(..., min_length=1)
    notes: str | None = Field(default=None, max_length=2000)
    customer_id: int | None = Field(default=None, ge=1)
    distributor_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)
    raw_token: str | None = Field(default=None, max_length=512)
    confirm_ineligible_product: bool = False
    audit_note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=128)
    # Shared for bulk provisional customer (per candidate display name is derived — same as steward defaults).
    region_id: int | None = Field(default=None, ge=1)
    channel_id: int | None = Field(default=None, ge=1)
    preferred_distributor_id: int | None = Field(default=None, ge=1)
    partner_tier: str | None = Field(default="unmanaged", max_length=32)
    provisional_notes_summary: str | None = Field(default=None, max_length=512)
    confirm_for_suspicious_distributor_token: bool = False
    provisional_distributor_code: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _payload_for_action(self) -> Self:
        cap = (
            DSI_BULK_STEWARD_MAX_IGNORE_CANDIDATE_IDS
            if self.action == "ignore"
            else DSI_BULK_STEWARD_MAX_CANDIDATE_IDS
        )
        if len(self.candidate_ids) > cap:
            raise ValueError(
                f"candidate_ids exceeds maximum of {cap} for action {self.action!r} "
                f"(received {len(self.candidate_ids)})"
            )
        if self.action == "map_customer":
            if self.customer_id is None:
                raise ValueError("customer_id is required for map_customer")
        elif self.action == "map_distributor":
            if self.distributor_id is None:
                raise ValueError("distributor_id is required for map_distributor")
        elif self.action == "resolve_product":
            if self.product_id is None:
                raise ValueError("product_id is required for resolve_product")
        return self


def _dsi_bulk_totals_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_idx = [r for r in rows if r.get("ok")]
    rows_affected = sum(int(r.get("row_count") or 0) for r in ok_idx)
    units = sum(float(r.get("total_units") or 0) for r in ok_idx)
    value = sum(float(r.get("total_reported_value") or 0) for r in ok_idx)
    return {
        "ok_count": len(ok_idx),
        "not_ok_count": len(rows) - len(ok_idx),
        "staging_rows_affected": rows_affected,
        "total_units_affected": units,
        "total_reported_value_affected": value,
    }


@router.post("/import-jobs/{job_id}/dsi-steward-bulk-preview", status_code=200)
async def dsi_steward_bulk_preview(job_id: int, body: DsiBulkStewardBody, db: AsyncSession = Depends(get_db)):
    await _assert_dsi_import_job(db, job_id)
    res = await db.execute(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.id.in_(body.candidate_ids),
        )
    )
    found = {c.id: c for c in res.scalars().all()}
    results: list[dict[str, Any]] = []
    for cid in body.candidate_ids:
        if cid not in found:
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "skip_reason": "not_found_or_wrong_job",
                    "detail": "Candidate not found for this job",
                }
            )
            continue
        cand = found[cid]
        if body.action == "ignore":
            pv = await preview_ignore_dsi_candidate(cand, notes=body.notes)
        elif body.action == "map_customer":
            pv = await preview_map_dsi_customer(
                db,
                cand,
                customer_id=int(body.customer_id or 0),
                raw_token=body.raw_token,
            )
        elif body.action == "map_distributor":
            pv = await preview_map_dsi_distributor(
                db,
                cand,
                distributor_id=int(body.distributor_id or 0),
                raw_token=body.raw_token,
            )
        elif body.action == "create_provisional_customer":
            er, ec = await _bulk_effective_provisional_geo(
                db, cand, body.region_id, body.channel_id, import_job_id=job_id
            )
            pv = await preview_create_provisional_dsi_customer(
                db,
                cand,
                display_name_override=None,
                region_id=er,
                channel_id=ec,
                preferred_distributor_id=body.preferred_distributor_id,
                partner_tier=body.partner_tier,
                notes_summary=body.provisional_notes_summary,
            )
        elif body.action == "create_provisional_distributor":
            pv = await preview_create_provisional_dsi_distributor(
                db,
                cand,
                display_name_override=None,
                distributor_code_override=body.provisional_distributor_code,
                confirm_for_suspicious_token=body.confirm_for_suspicious_distributor_token,
            )
        else:
            pv = await preview_resolve_dsi_product(
                db,
                cand,
                product_id=int(body.product_id or 0),
                raw_token=body.raw_token,
                confirm_ineligible_product=body.confirm_ineligible_product,
                audit_note=body.audit_note,
            )
        results.append(
            {
                "candidate_id": cand.id,
                "entity_type": cand.entity_type,
                "candidate_status": cand.status,
                "row_count": cand.row_count,
                "total_units": float(cand.total_units) if cand.total_units is not None else None,
                "total_reported_value": float(cand.total_reported_value)
                if cand.total_reported_value is not None
                else None,
                "sample_raw_preview": (cand.sample_raw_values or [])[:3]
                if isinstance(cand.sample_raw_values, list)
                else [],
                **pv,
            }
        )
    return {
        "import_job_id": job_id,
        "action": body.action,
        "results": results,
        "totals": _dsi_bulk_totals_from_rows(results),
    }


def _dsi_bulk_provisional_payload_from_body(body: DsiBulkStewardBody) -> dict[str, Any]:
    return {
        "candidate_ids": list(body.candidate_ids),
        "region_id": body.region_id,
        "channel_id": body.channel_id,
        "preferred_distributor_id": body.preferred_distributor_id,
        "partner_tier": body.partner_tier,
        "provisional_notes_summary": body.provisional_notes_summary,
    }


def _enqueue_dsi_bulk_provisional_customers(
    job_id: int,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    """Return (task_id, async_poll_required). When async_poll_required is False, result is already in dev store."""
    from app.services.task_run_ledger import (
        ENTITY_IMPORT_JOB,
        TRANSPORT_BROKER,
        TRANSPORT_INLINE_SYNC,
        TRANSPORT_IN_PROCESS_THREAD,
        create_queued_task_run,
        run_inline_with_ledger,
        spawn_in_process_thread_with_ledger,
    )

    settings = get_settings()
    task_name = "imports.dsi_bulk_provisional_customers"

    def _run_sync() -> dict[str, Any]:
        with SessionLocal() as session:
            return run_dsi_bulk_provisional_customers_sync(session, job_id, payload)

    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        return task_id, True
    except Exception:
        logger.exception(
            "dsi_bulk_provisional: Celery enqueue failed job_id=%s task=%s", job_id, task_name
        )
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"dev-bulk-prov-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_id,
                task_name=task_name,
                entity_type=ENTITY_IMPORT_JOB,
                entity_id=job_id,
                transport=TRANSPORT_IN_PROCESS_THREAD,
            )

            def _in_process() -> None:
                try:
                    out = _run_sync()
                    _dev_dsi_bulk_task_results[task_id] = {
                        "state": "SUCCESS",
                        "result": out,
                    }
                except Exception as exc:
                    logger.exception(
                        "dsi_bulk_provisional in-process thread failed job_id=%s task_id=%s",
                        job_id,
                        task_id,
                    )
                    _dev_dsi_bulk_task_results[task_id] = {
                        "state": "FAILURE",
                        "error": str(exc)[:800],
                    }
                    raise

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: dsi_bulk_provisional job_id=%s — in-process thread (DEV ONLY).",
                job_id,
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_id,
                thread_name=f"dsi-bulk-prov-{job_id}",
                target=_in_process,
            )
            return task_id, True

        task_id = f"sync-bulk-prov-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_INLINE_SYNC,
        )

        def _inline() -> dict[str, Any]:
            out = _run_sync()
            _dev_dsi_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
            return out

        run_inline_with_ledger(task_id, _inline)
        return task_id, False


def _dsi_bulk_ignore_payload_from_body(body: DsiBulkStewardBody) -> dict[str, Any]:
    return {
        "candidate_ids": list(body.candidate_ids),
        "notes": body.notes,
    }


def _enqueue_dsi_bulk_ignore(
    job_id: int,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    """Return (task_id, async_poll_required). When async_poll_required is False, result is already in dev store."""
    from app.services.task_run_ledger import (
        ENTITY_IMPORT_JOB,
        TRANSPORT_BROKER,
        TRANSPORT_INLINE_SYNC,
        TRANSPORT_IN_PROCESS_THREAD,
        create_queued_task_run,
        run_inline_with_ledger,
        spawn_in_process_thread_with_ledger,
    )

    settings = get_settings()
    task_name = "imports.dsi_bulk_ignore"

    def _run_sync() -> dict[str, Any]:
        with SessionLocal() as session:
            return run_dsi_bulk_ignore_sync(
                session,
                job_id,
                list(payload.get("candidate_ids") or []),
                notes=payload.get("notes"),
            )

    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        return task_id, True
    except Exception:
        logger.exception("dsi_bulk_ignore: Celery enqueue failed job_id=%s task=%s", job_id, task_name)
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"dev-bulk-ignore-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_id,
                task_name=task_name,
                entity_type=ENTITY_IMPORT_JOB,
                entity_id=job_id,
                transport=TRANSPORT_IN_PROCESS_THREAD,
            )

            def _in_process() -> None:
                try:
                    out = _run_sync()
                    _dev_dsi_bulk_task_results[task_id] = {
                        "state": "SUCCESS",
                        "result": out,
                    }
                except Exception as exc:
                    logger.exception(
                        "dsi_bulk_ignore in-process thread failed job_id=%s task_id=%s",
                        job_id,
                        task_id,
                    )
                    _dev_dsi_bulk_task_results[task_id] = {
                        "state": "FAILURE",
                        "error": str(exc)[:800],
                    }
                    raise

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: dsi_bulk_ignore job_id=%s — in-process thread (DEV ONLY).",
                job_id,
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_id,
                thread_name=f"dsi-bulk-ignore-{job_id}",
                target=_in_process,
            )
            return task_id, True

        task_id = f"sync-bulk-ignore-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_INLINE_SYNC,
        )

        def _inline() -> dict[str, Any]:
            out = _run_sync()
            _dev_dsi_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
            return out

        run_inline_with_ledger(task_id, _inline)
        return task_id, False


@router.post("/import-jobs/{job_id}/dsi-steward-bulk-provisional-customers/apply-async", status_code=202)
async def dsi_steward_bulk_provisional_apply_async(
    job_id: int, body: DsiBulkStewardBody, db: AsyncSession = Depends(get_db)
):
    """Enqueue batch provisional customer creation (single DB commit; poll task for completion)."""
    await _assert_dsi_import_job(db, job_id)
    if body.action != "create_provisional_customer":
        raise HTTPException(
            status_code=400,
            detail="action must be create_provisional_customer for this endpoint",
        )
    payload = _dsi_bulk_provisional_payload_from_body(body)
    task_id, async_poll = _enqueue_dsi_bulk_provisional_customers(job_id, payload)
    job = await db.get(ImportJob, job_id)
    if job:
        set_task_slot_on_job(
            job,
            SLOT_DSI_BULK,
            task_id=task_id,
            async_poll=async_poll,
            kind="dsi_bulk_provisional_customers",
        )
        await db.commit()
    return {
        "import_job_id": job_id,
        "task_id": task_id,
        "async_poll": async_poll,
        "action": body.action,
    }


@router.post("/import-jobs/{job_id}/dsi-steward-bulk-ignore/apply-async", status_code=202)
async def dsi_steward_bulk_ignore_apply_async(
    job_id: int, body: DsiBulkStewardBody, db: AsyncSession = Depends(get_db)
):
    """Enqueue batch ignore (single DB commit + one staging demotion pass; poll task for completion)."""
    await _assert_dsi_import_job(db, job_id)
    if body.action != "ignore":
        raise HTTPException(
            status_code=400,
            detail="action must be ignore for this endpoint",
        )
    payload = _dsi_bulk_ignore_payload_from_body(body)
    task_id, async_poll = _enqueue_dsi_bulk_ignore(job_id, payload)
    job = await db.get(ImportJob, job_id)
    if job:
        set_task_slot_on_job(
            job,
            SLOT_DSI_BULK,
            task_id=task_id,
            async_poll=async_poll,
            kind=KIND_DSI_BULK_IGNORE,
        )
        await db.commit()
    return {
        "import_job_id": job_id,
        "task_id": task_id,
        "async_poll": async_poll,
        "action": body.action,
    }


@router.get("/import-jobs/{job_id}/dsi-steward-bulk-task/{task_id}", status_code=200)
async def dsi_steward_bulk_task_status(job_id: int, task_id: str) -> dict[str, Any]:
    """Poll Celery (or dev in-process) bulk steward task state and result."""
    dev_hit = _dev_dsi_bulk_task_results.get(task_id)
    if dev_hit is not None:
        state = dev_hit.get("state", "SUCCESS")
        if state in ("SUCCESS", "FAILURE"):
            _dev_dsi_bulk_task_results.pop(task_id, None)
        out: dict[str, Any] = {
            "import_job_id": job_id,
            "task_id": task_id,
            "state": state,
        }
        if state == "SUCCESS":
            out["result"] = dev_hit.get("result")
        else:
            out["error"] = dev_hit.get("error")
        return out

    from celery.result import AsyncResult

    def _read() -> tuple[str, Any]:
        r = AsyncResult(task_id, app=celery_app)
        return r.state, r.info

    task_state, info = await asyncio.to_thread(_read)
    progress: dict[str, Any] = {
        "import_job_id": job_id,
        "task_id": task_id,
        "state": task_state,
    }
    if task_state == "PROGRESS" and isinstance(info, dict):
        progress["phase"] = info.get("phase")
        progress["phase_label"] = info.get("phase_label")
        progress["current_row"] = info.get("current_row", 0)
        progress["total_rows"] = info.get("total_rows", 0)
        progress["pct"] = info.get("pct", 0)
    elif task_state == "SUCCESS":
        from celery.result import AsyncResult as _AR

        raw_result = await asyncio.to_thread(lambda: _AR(task_id, app=celery_app).result)
        progress["result"] = raw_result if isinstance(raw_result, dict) else None
    elif task_state == "FAILURE":
        progress["error"] = str(info)[:800] if info is not None else "Task failed"

    if task_state in ("SUCCESS", "FAILURE", "REVOKED"):

        def _clear_bulk_meta() -> None:
            from app.services.imports.import_job_background_metadata import (
                clear_background_task_metadata_on_job,
            )

            with SessionLocal() as sess:
                job = sess.get(ImportJob, job_id)
                if job and clear_background_task_metadata_on_job(job):
                    sess.commit()

        await asyncio.to_thread(_clear_bulk_meta)

    return progress


@router.post("/import-jobs/{job_id}/dsi-steward-bulk-apply", status_code=200)
async def dsi_steward_bulk_apply(job_id: int, body: DsiBulkStewardBody, db: AsyncSession = Depends(get_db)):
    await _assert_dsi_import_job(db, job_id)
    if body.action == "create_provisional_customer":
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Bulk provisional customer apply must use "
                    "POST .../dsi-steward-bulk-provisional-customers/apply-async and poll "
                    ".../dsi-steward-bulk-task/{task_id}."
                ),
                "code": "use_async_bulk_provisional",
            },
        )
    if body.action == "ignore":
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Bulk ignore apply must use "
                    "POST .../dsi-steward-bulk-ignore/apply-async and poll "
                    ".../dsi-steward-bulk-task/{task_id}."
                ),
                "code": "use_async_bulk_ignore",
            },
        )
    results: list[dict[str, Any]] = []
    for cid in body.candidate_ids:
        cand = await db.get(ImportEntityMappingCandidate, cid)
        if cand is None or cand.import_job_id != job_id:
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "detail": "Candidate not found for this job",
                    "row_count": None,
                    "total_units": None,
                    "total_reported_value": None,
                }
            )
            continue
        rc = cand.row_count
        tu = float(cand.total_units) if cand.total_units is not None else None
        trv = float(cand.total_reported_value) if cand.total_reported_value is not None else None
        try:
            if body.action == "map_customer":
                out = await execute_map_dsi_customer(
                    db,
                    cand,
                    customer_id=int(body.customer_id or 0),
                    raw_token=body.raw_token,
                )
            elif body.action == "map_distributor":
                out = await execute_map_dsi_distributor(
                    db,
                    cand,
                    distributor_id=int(body.distributor_id or 0),
                    raw_token=body.raw_token,
                )
            elif body.action == "create_provisional_customer":
                er, ec = await _bulk_effective_provisional_geo(
                    db, cand, body.region_id, body.channel_id, import_job_id=job_id
                )
                out = await execute_create_provisional_dsi_customer(
                    db,
                    cand,
                    display_name_override=None,
                    region_id=er,
                    channel_id=ec,
                    preferred_distributor_id=body.preferred_distributor_id,
                    partner_tier=body.partner_tier,
                    notes_summary=body.provisional_notes_summary,
                )
            elif body.action == "create_provisional_distributor":
                out = await execute_create_provisional_dsi_distributor(
                    db,
                    cand,
                    display_name_override=None,
                    distributor_code_override=body.provisional_distributor_code,
                    confirm_for_suspicious_token=body.confirm_for_suspicious_distributor_token,
                )
            else:
                out = await execute_resolve_dsi_product(
                    db,
                    cand,
                    product_id=int(body.product_id or 0),
                    raw_token=body.raw_token,
                    confirm_ineligible_product=body.confirm_ineligible_product,
                    audit_note=body.audit_note,
                    idempotency_key=body.idempotency_key,
                )
            results.append(
                {
                    "candidate_id": cid,
                    "ok": True,
                    "entity_type": cand.entity_type,
                    "result": out,
                    "row_count": rc,
                    "total_units": tu,
                    "total_reported_value": trv,
                }
            )
        except StewardOpError as exc:
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "detail": exc.detail,
                    "row_count": rc,
                    "total_units": tu,
                    "total_reported_value": trv,
                }
            )
    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "action": body.action,
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
        "totals": _dsi_bulk_totals_from_rows(results),
    }


def _enqueue_dsi_resolution_plan_compute(
    job_id: int,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    from app.services.imports.dsi_resolution_plan_enqueue import enqueue_dsi_resolution_plan_compute

    return enqueue_dsi_resolution_plan_compute(job_id, payload)


def _dsi_resolution_plan_compute_payload_from_body(body: DsiResolutionPlanGenerateBody) -> dict[str, Any]:
    return {
        "candidate_ids": list(body.candidate_ids) if body.candidate_ids else None,
        "default_region_id": body.default_region_id,
        "default_channel_id": body.default_channel_id,
    }


@router.post("/import-jobs/{job_id}/dsi-resolution-plan/compute-async", status_code=202)
async def dsi_resolution_plan_compute_async(
    job_id: int, body: DsiResolutionPlanGenerateBody, db: AsyncSession = Depends(get_db)
):
    """Enqueue resolution-plan generation (Celery); poll dsi-steward-bulk-task/{task_id} for the plan."""
    await _assert_dsi_import_job(db, job_id)
    job = await db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    payload = _dsi_resolution_plan_compute_payload_from_body(body)
    reused_tid = reusable_dsi_bulk_task_id(job, kind=KIND_DSI_RESOLUTION_PLAN_COMPUTE)
    if reused_tid:
        return {
            "import_job_id": job_id,
            "task_id": reused_tid,
            "async_poll": True,
            "async": True,
            "reused": True,
        }

    def _assert_allowed(sess: Session) -> None:
        j = sess.get(ImportJob, job_id)
        if j is None:
            raise ValueError("Import job not found")
        assert_dsi_steward_background_dispatch_allowed(sess, j)

    try:
        await db.run_sync(_assert_allowed)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    task_id, async_poll = _enqueue_dsi_resolution_plan_compute(job_id, payload)
    set_task_slot_on_job(
        job,
        SLOT_DSI_BULK,
        task_id=task_id,
        async_poll=async_poll,
        kind="dsi_resolution_plan_compute",
        candidate_count=len(body.candidate_ids or []),
    )
    await db.commit()
    return {
        "import_job_id": job_id,
        "task_id": task_id,
        "async_poll": async_poll,
        "async": True,
    }


@router.post("/import-jobs/{job_id}/dsi-resolution-plan", status_code=200)
async def dsi_resolution_plan_generate(
    job_id: int, body: DsiResolutionPlanGenerateBody, db: AsyncSession = Depends(get_db)
):
    """Transient steward resolution plan for DSI mapping candidates (same rules as validation/steward)."""
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return build_dsi_resolution_plan_sync(
            sess,
            job_id,
            candidate_ids=body.candidate_ids,
            default_region_id=body.default_region_id,
            default_channel_id=body.default_channel_id,
        )

    try:
        return await db.run_sync(_work)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import-jobs/{job_id}/dsi-resolution-plan/effective", status_code=200)
async def dsi_resolution_plan_effective(
    job_id: int, body: DsiResolutionPlanEffectiveBody, db: AsyncSession = Depends(get_db)
):
    """Baseline DSI plan merged with per-row overrides (read-only; refreshes ready/blocker state)."""
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return build_dsi_resolution_plan_effective_sync(
            sess,
            job_id,
            candidate_ids=body.candidate_ids,
            default_region_id=body.default_region_id,
            default_channel_id=body.default_channel_id,
            overrides=[o.model_dump(exclude_unset=True) for o in body.overrides],
            global_confirm_suspicious_distributor=body.confirm_for_suspicious_distributor_token,
        )

    try:
        return await db.run_sync(_work)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _dsi_resolution_plan_apply_payload_from_body(body: DsiResolutionPlanApplyBody) -> dict[str, Any]:
    ov_list = [o.model_dump(exclude_unset=True) for o in (body.overrides or [])]
    return {
        "candidate_ids": list(body.candidate_ids),
        "default_region_id": body.default_region_id,
        "default_channel_id": body.default_channel_id,
        "partner_tier": body.partner_tier,
        "provisional_notes_summary": body.provisional_notes_summary,
        "confirm_for_suspicious_distributor_token": body.confirm_for_suspicious_distributor_token,
        "overrides": ov_list or None,
    }


def _enqueue_dsi_resolution_plan_apply(
    job_id: int,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    """Return (task_id, async_poll_required)."""
    from app.services.imports.dsi_resolution_plan_enqueue import enqueue_dsi_resolution_plan_apply

    return enqueue_dsi_resolution_plan_apply(job_id, payload, detach_from_caller=False)


@router.post("/import-jobs/{job_id}/dsi-resolution-plan/apply-async", status_code=202)
async def dsi_resolution_plan_apply_async(
    job_id: int, body: DsiResolutionPlanApplyBody, db: AsyncSession = Depends(get_db)
):
    """Enqueue resolution-plan apply (Celery); poll dsi-steward-bulk-task/{task_id} for progress."""
    await _assert_dsi_import_job(db, job_id)
    job = await db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    def _assert_allowed(sess: Session) -> None:
        j = sess.get(ImportJob, job_id)
        if j is None:
            raise ValueError("Import job not found")
        assert_dsi_steward_background_dispatch_allowed(sess, j)

    try:
        await db.run_sync(_assert_allowed)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    payload = _dsi_resolution_plan_apply_payload_from_body(body)
    task_id, async_poll = _enqueue_dsi_resolution_plan_apply(job_id, payload)
    set_task_slot_on_job(
        job,
        SLOT_DSI_BULK,
        task_id=task_id,
        async_poll=async_poll,
        kind="dsi_resolution_plan_apply",
        candidate_count=len(body.candidate_ids),
    )
    await db.commit()
    return {
        "import_job_id": job_id,
        "task_id": task_id,
        "async_poll": async_poll,
    }


@router.post("/import-jobs/{job_id}/dsi-resolution-plan/apply", status_code=200)
async def dsi_resolution_plan_apply_endpoint(
    job_id: int, body: DsiResolutionPlanApplyBody, db: AsyncSession = Depends(get_db)
):
    """Apply steward actions synchronously (small batches only; prefer apply-async for bulk)."""
    await _assert_dsi_import_job(db, job_id)
    if len(body.candidate_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "More than 50 candidates — use POST .../dsi-resolution-plan/apply-async "
                    "and poll .../dsi-steward-bulk-task/{task_id}."
                ),
                "code": "use_async_resolution_plan_apply",
            },
        )
    job = await db.get(ImportJob, job_id)
    if job:

        def _assert_allowed(sess: Session) -> None:
            j = sess.get(ImportJob, job_id)
            if j is None:
                raise ValueError("Import job not found")
            assert_dsi_steward_background_dispatch_allowed(sess, j)

        try:
            await db.run_sync(_assert_allowed)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    payload = _dsi_resolution_plan_apply_payload_from_body(body)
    return run_dsi_resolution_plan_apply_sync(job_id, payload)


@router.post("/import-jobs/{job_id}/dsi-apply-complete", status_code=200)
async def dsi_apply_complete_to_loaded(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
) -> dict[str, Any]:
    """Refresh DSI staging resolutions, upsert facts, and promote job to ``loaded`` when rules pass."""
    await _assert_dsi_import_job(db, job_id)

    def _work() -> dict[str, Any]:
        with SessionLocal() as s:
            return complete_dsi_import_job_to_loaded(s, job_id)

    try:
        return await asyncio.to_thread(_work)
    except DsiApplyCompletionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import-jobs/{job_id}/revalidate-distributor-sales-inventory")
async def revalidate_dsi_import_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Re-run DSI import validation via Celery (same pipeline as validate)."""
    await _assert_dsi_import_job(db, job_id)

    from app.api.v1.endpoints.imports import (
        _enqueue_import_pipeline_job,
        _persist_pipeline_celery_task_id,
        _prepare_dsi_pipeline_dispatch,
    )

    _prepare_dsi_pipeline_dispatch(job_id)

    dispatched, dsi_task_id = _enqueue_import_pipeline_job(
        job_id,
        log_label="DSI revalidate",
        in_process_thread_name=f"dsi-revalidate-{job_id}",
    )

    if dispatched and dsi_task_id:
        _persist_pipeline_celery_task_id(job_id, dsi_task_id)

    job = await db.get(ImportJob, job_id)
    if dispatched:
        return {
            "async": True,
            "ok": True,
            "import_job_id": job_id,
            "task_id": dsi_task_id,
            "status": job.status if job else "running",
            "stage": job.stage if job else None,
            "template_slug": job.template_slug if job else "distributor_inventory",
            "message": "Revalidation started in the background worker.",
        }

    if job and job.status == "failed":
        raise HTTPException(
            status_code=422,
            detail=job.error_summary or "Import job failed during revalidation.",
        )

    return {
        "async": False,
        "ok": True,
        "import_job_id": job_id,
        "status": job.status if job else None,
        "stage": job.stage if job else None,
        "template_slug": job.template_slug if job else "distributor_inventory",
    }


@router.get("/import-jobs/{job_id}/dsi-channel-geographic-evidence", status_code=200)
async def dsi_channel_geographic_evidence(job_id: int, db: AsyncSession = Depends(get_db)):
    """Channel file values that look like countries/regions (hint evidence, not RTM mapping)."""
    await _assert_dsi_import_job(db, job_id)

    from app.services.imports.dsi_channel_geographic_evidence import (
        collect_dsi_channel_geographic_evidence_sync,
    )

    def _work(sess: Session) -> dict[str, Any]:
        return collect_dsi_channel_geographic_evidence_sync(sess, job_id)

    try:
        return await db.run_sync(_work)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc


@router.get("/import-jobs/{job_id}/dsi-unresolved-geo-tokens", status_code=200)
async def dsi_unresolved_geo_tokens(job_id: int, db: AsyncSession = Depends(get_db)):
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return collect_dsi_job_unresolved_geo_tokens_sync(sess, job_id)

    try:
        return await db.run_sync(_work)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc


class DsiGeoStewardChannelCreateBody(BaseModel):
    channel_code: str = Field(..., min_length=1, max_length=32)
    channel_name: str = Field(..., min_length=1, max_length=256)
    raw_token: str = Field(..., min_length=1, max_length=512)
    notes: str | None = Field(default=None, max_length=2000)


class DsiGeoStewardChannelAliasBody(BaseModel):
    channel_id: int = Field(..., ge=1)
    raw_token: str = Field(..., min_length=1, max_length=512)
    notes: str | None = Field(default=None, max_length=2000)


class DsiGeoStewardRegionCreateBody(BaseModel):
    region_code: str = Field(..., min_length=1, max_length=32)
    region_name: str = Field(..., min_length=1, max_length=256)
    raw_token: str = Field(..., min_length=1, max_length=512)
    notes: str | None = Field(default=None, max_length=2000)


class DsiGeoStewardRegionAliasBody(BaseModel):
    region_id: int = Field(..., ge=1)
    raw_token: str = Field(..., min_length=1, max_length=512)
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/import-jobs/{job_id}/dsi-geo-steward/channel-create", status_code=201)
async def dsi_geo_steward_channel_create(
    job_id: int,
    body: DsiGeoStewardChannelCreateBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return create_dim_channel_with_source_alias_sync(
            sess,
            import_job_id=job_id,
            channel_code=body.channel_code,
            channel_name=body.channel_name,
            raw_token=body.raw_token,
            notes=body.notes,
        )

    try:
        out = await db.run_sync(_work)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return out


@router.post("/import-jobs/{job_id}/dsi-geo-steward/channel-alias", status_code=201)
async def dsi_geo_steward_channel_alias(
    job_id: int,
    body: DsiGeoStewardChannelAliasBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return create_channel_source_token_alias_sync(
            sess,
            import_job_id=job_id,
            channel_id=body.channel_id,
            raw_token=body.raw_token,
            notes=body.notes,
        )

    try:
        out = await db.run_sync(_work)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return out


@router.post("/import-jobs/{job_id}/dsi-geo-steward/region-create", status_code=201)
async def dsi_geo_steward_region_create(
    job_id: int,
    body: DsiGeoStewardRegionCreateBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return create_dim_region_with_source_alias_sync(
            sess,
            import_job_id=job_id,
            region_code=body.region_code,
            region_name=body.region_name,
            raw_token=body.raw_token,
            notes=body.notes,
        )

    try:
        out = await db.run_sync(_work)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return out


@router.post("/import-jobs/{job_id}/dsi-geo-steward/region-alias", status_code=201)
async def dsi_geo_steward_region_alias(
    job_id: int,
    body: DsiGeoStewardRegionAliasBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return create_region_source_token_alias_sync(
            sess,
            import_job_id=job_id,
            region_id=body.region_id,
            raw_token=body.raw_token,
            notes=body.notes,
        )

    try:
        out = await db.run_sync(_work)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return out


class DsiGeoRegisterRegionHintBody(BaseModel):
    raw_token: str = Field(..., min_length=1, max_length=512)
    iso_alpha2: str | None = Field(default=None, min_length=2, max_length=2)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/import-jobs/{job_id}/dsi-geo-steward/create-prefill", status_code=200)
async def dsi_geo_steward_create_prefill(
    job_id: int,
    raw_token: str = Query(..., min_length=1),
    dimension: str = Query(..., pattern="^(region|channel)$"),
    normalized_token: str | None = Query(default=None, max_length=512),
    db: AsyncSession = Depends(get_db),
):
    await _assert_dsi_import_job(db, job_id)
    dim = (dimension or "region").strip().lower()
    if dim not in ("region", "channel"):
        raise HTTPException(status_code=400, detail="dimension must be region or channel")

    def _work(_sess: Session) -> dict[str, str]:
        pre = suggest_geo_create_prefill_sync(
            raw_token=raw_token,
            dimension=dim,
            normalized_token=normalized_token,
        )
        return {
            "suggested_code": pre["code"],
            "suggested_name": pre["name"],
            "prefill_source": pre["prefill_source"],
        }

    return await db.run_sync(_work)


@router.post("/import-jobs/{job_id}/dsi-geo-steward/region-register-from-hint", status_code=201)
async def dsi_geo_steward_region_register_from_hint(
    job_id: int,
    body: DsiGeoRegisterRegionHintBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    """Create or resolve ISO region and alias a file token (channel geographic hint — not channel→region mapping)."""
    await _assert_dsi_import_job(db, job_id)

    def _work(sess: Session) -> dict[str, Any]:
        return register_region_from_geographic_hint_sync(
            sess,
            import_job_id=job_id,
            raw_token=body.raw_token,
            iso_alpha2=body.iso_alpha2,
            notes=body.notes,
        )

    try:
        out = await db.run_sync(_work)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return out


class DsiGeoStewardBulkItem(BaseModel):
    kind: str = Field(..., pattern="^(channel|region)$")
    raw_token: str = Field(..., min_length=1, max_length=512)
    normalized_token: str | None = Field(default=None, max_length=512)
    code: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, max_length=256)
    iso_alpha2: str | None = Field(default=None, min_length=2, max_length=2)
    notes: str | None = Field(default=None, max_length=2000)


class DsiGeoStewardBulkBody(BaseModel):
    action: str = Field(..., pattern="^(register_region_from_hint|register_from_file)$")
    items: list[DsiGeoStewardBulkItem] = Field(..., min_length=1, max_length=500)


@router.post("/import-jobs/{job_id}/dsi-geo-steward/bulk-apply", status_code=200)
async def dsi_geo_steward_bulk_apply(
    job_id: int,
    body: DsiGeoStewardBulkBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    """Bulk register region/channel catalog rows + aliases for unresolved geo file tokens."""
    await _assert_dsi_import_job(db, job_id)

    from app.services.imports.dsi_geo_steward_bulk_sync import apply_dsi_geo_steward_bulk_sync

    def _work(sess: Session) -> dict[str, Any]:
        return apply_dsi_geo_steward_bulk_sync(
            sess,
            import_job_id=job_id,
            action=body.action,  # type: ignore[arg-type]
            items=[item.model_dump() for item in body.items],
        )

    try:
        out = await db.run_sync(_work)
    except StewardOpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return out


class CustomerSourceTokenAliasCreate(BaseModel):
    """Explicit approval: map a raw distributor-reported customer/dealer token to an existing dim_customer row."""

    customer_id: int = Field(..., ge=1)
    raw_token: str = Field(..., min_length=1, max_length=512)
    source_definition_id: int | None = None
    distributor_id: int | None = None
    dealer_group_token: str | None = Field(default=None, max_length=512)
    notes: str | None = None
    created_from_import_job_id: int | None = None
    import_entity_mapping_candidate_id: int | None = None


@router.post("/customer-source-token-aliases", status_code=201)
async def create_customer_source_token_alias(body: CustomerSourceTokenAliasCreate, db: AsyncSession = Depends(get_db)):
    nt = _norm_key(body.raw_token)
    if not nt:
        raise HTTPException(status_code=400, detail="raw_token is empty after normalization")
    row = CustomerSourceTokenAlias(
        customer_id=body.customer_id,
        raw_token=body.raw_token.strip()[:512],
        normalized_token=nt[:512],
        source_definition_id=body.source_definition_id,
        distributor_id=body.distributor_id,
        dealer_group_token=(body.dealer_group_token.strip()[:512] if body.dealer_group_token else None),
        status="approved",
        notes=body.notes,
        created_from_import_job_id=body.created_from_import_job_id,
        import_entity_mapping_candidate_id=body.import_entity_mapping_candidate_id,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create alias (invalid customer or source reference)")
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "normalized_token": row.normalized_token,
        "source_definition_id": row.source_definition_id,
        "distributor_id": row.distributor_id,
        "status": row.status,
    }
