import asyncio
import secrets
from datetime import datetime, timezone

from typing import Any, Literal

from typing_extensions import Self

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimRegion
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob
from app.models.mapping import EntityMappingQueue
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import (
    StewardOpError,
    execute_ignore_dsi_candidate,
    execute_map_dsi_customer,
    execute_map_dsi_distributor,
    execute_resolve_dsi_product,
    preview_ignore_dsi_candidate,
    preview_map_dsi_customer,
    preview_map_dsi_distributor,
    preview_resolve_dsi_product,
)

router = APIRouter()


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
async def list_distributor_si_mapping_candidates(job_id: int, db: AsyncSession = Depends(get_db)):
    """Aggregated unresolved distributor/product/customer tokens from a distributor sales & inventory import job."""
    res = await db.execute(
        select(ImportEntityMappingCandidate)
        .where(ImportEntityMappingCandidate.import_job_id == job_id)
        .order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.normalized_key)
    )
    rows = res.scalars().all()
    return [
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
            "match_reason": r.match_reason,
            "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
            "status": r.status,
            "context": r.context,
            "created_at": r.created_at.isoformat() if r.created_at is not None else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
        }
        for r in rows
    ]


def _first_sample_raw(candidate: ImportEntityMappingCandidate) -> str:
    samples = candidate.sample_raw_values or []
    for s in samples:
        if isinstance(s, str) and s.strip():
            return s.strip()[:512]
    if candidate.normalized_key and candidate.normalized_key != "__blank__":
        return candidate.normalized_key[:512]
    return ""


def _source_customer_alias_raw_for_dsi_candidate(candidate: ImportEntityMappingCandidate) -> str:
    """Raw source customer name / dealer column evidence for CustomerSourceTokenAlias (not Dealer Name Group).

    Prefer structured ``context.source_customer_name_raw_samples`` from DSI aggregation; fall back to
    composite ``sample_raw_values`` / ``normalized_key`` only when needed.
    """
    ctx = candidate.context if isinstance(candidate.context, dict) else {}
    samples = ctx.get("source_customer_name_raw_samples")
    if isinstance(samples, list):
        for s in samples:
            if isinstance(s, str) and s.strip():
                return s.strip()[:512]
    return _first_sample_raw(candidate)


def _blank_customer_normalized_key(norm: str) -> bool:
    t = (norm or "").strip().lower()
    return t in ("", "__blank__", "none", "n/a", "na", "unknown")


DISTRIBUTOR_PROVISIONAL_SUSPICIOUS = frozenset(
    {
        "open channel",
        "open_channel",
        "cash sale",
        "internal",
        "n/a",
        "na",
        "tbd",
        "unknown",
        "misc",
        "blank",
        "",
    }
)


async def _generate_tmp_distributor_code(db: AsyncSession) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _ in range(8):
        candidate = f"TMP-DIST-{stamp}-{secrets.token_hex(2).upper()}"
        exists = await db.execute(select(DimDistributor.id).where(DimDistributor.code == candidate))
        if exists.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(status_code=503, detail="Unable to generate a temporary distributor code; retry.")


async def _generate_tmp_customer_code(db: AsyncSession) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _ in range(8):
        candidate = f"TMP-CUST-{stamp}-{secrets.token_hex(2).upper()}"
        exists = await db.execute(select(DimCustomer.id).where(DimCustomer.code == candidate))
        if exists.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(status_code=503, detail="Unable to generate a temporary customer code; retry.")


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


class MapCustomerBody(BaseModel):
    customer_id: int = Field(..., ge=1)
    raw_token: str | None = Field(default=None, max_length=512)


class CreateProvisionalCustomerBody(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)
    region_id: int = Field(..., ge=1)
    channel_id: int = Field(..., ge=1)
    preferred_distributor_id: int | None = None
    partner_tier: str | None = Field(default="unmanaged", max_length=32)
    notes_summary: str | None = Field(default=None, max_length=512)


class MarkOpenChannelBody(BaseModel):
    """Assign Open Channel dim_customer via alias. Named dealers require explicit confirmation."""

    confirm_for_named_dealer: bool = False
    confirm_for_strategic_channel_hint: bool = False


class IgnoreCandidateBody(BaseModel):
    notes: str | None = None


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


@router.post("/import-candidates/{candidate_id}/create-provisional-customer", status_code=200)
async def create_provisional_customer_from_dsi_candidate(
    candidate_id: int, body: CreateProvisionalCustomerBody, db: AsyncSession = Depends(get_db)
):
    cand = await _get_dsi_candidate_or_404(candidate_id, db)
    if cand.entity_type != "customer_dealer_token":
        raise HTTPException(status_code=400, detail="Candidate entity_type is not customer_dealer_token")
    region = await db.get(DimRegion, body.region_id)
    if not region:
        raise HTTPException(status_code=400, detail="Invalid region_id")
    channel = await db.get(DimChannel, body.channel_id)
    if not channel:
        raise HTTPException(status_code=400, detail="Invalid channel_id")
    pref = None
    if body.preferred_distributor_id is not None:
        pref = await db.get(DimDistributor, body.preferred_distributor_id)
        if not pref:
            raise HTTPException(status_code=400, detail="Invalid preferred_distributor_id")
    code = await _generate_tmp_customer_code(db)
    tier = (body.partner_tier or "unmanaged").strip().lower()
    if tier not in {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail", "unmanaged"}:
        raise HTTPException(status_code=400, detail="Invalid partner_tier")
    notes = (body.notes_summary or "").strip() or None
    base_note = f"Provisional customer created from DSI import candidate {cand.id} (job {cand.import_job_id})."
    merged_notes = f"{base_note} {notes}" if notes else base_note
    row = DimCustomer(
        code=code,
        name=body.display_name.strip(),
        customer_status="unverified",
        partner_tier=tier,
        notes_summary=merged_notes[:512],
        region_id=body.region_id,
        channel_id=body.channel_id,
        preferred_distributor_id=body.preferred_distributor_id,
    )
    db.add(row)
    await db.flush()
    raw = _source_customer_alias_raw_for_dsi_candidate(cand)
    if not raw:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Candidate has no usable raw token sample")
    nt = _norm_key(raw)
    alias = CustomerSourceTokenAlias(
        customer_id=row.id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        status="approved",
        notes=f"Alias from provisional customer create (candidate {cand.id})",
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    db.add(alias)
    try:
        cand.status = "resolved"
        cand.suggested_entity_id = row.id
        cand.match_reason = "steward_created_provisional_customer"
        await db.commit()
        await db.refresh(row)
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create customer or alias")
    return {
        "ok": True,
        "customer_id": row.id,
        "customer_code": row.code,
        "alias_id": alias.id,
        "candidate_id": cand.id,
    }


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
    nt = _norm_key(raw)
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
        return await execute_ignore_dsi_candidate(db, cand, notes=body.notes)
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
    if cand.entity_type != "distributor_token":
        raise HTTPException(status_code=400, detail="Candidate entity_type is not distributor_token")
    nt_check = _norm_key(_first_sample_raw(cand) or cand.normalized_key)
    if nt_check in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS and not body.confirm_for_suspicious_token:
        raise HTTPException(
            status_code=400,
            detail="Token looks like a placeholder or internal label; set confirm_for_suspicious_token=true to create a provisional distributor anyway.",
        )
    code = (body.distributor_code or "").strip() or await _generate_tmp_distributor_code(db)
    existing = await db.execute(select(DimDistributor.id).where(DimDistributor.code == code))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="distributor_code already exists; omit distributor_code to auto-generate")
    row = DimDistributor(code=code[:32], name=body.display_name.strip()[:256])
    db.add(row)
    await db.flush()
    raw = _first_sample_raw(cand)
    if not raw:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Candidate has no usable raw token sample")
    nt = _norm_key(raw)
    alias = DistributorSourceTokenAlias(
        distributor_id=row.id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Provisional distributor from candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        cand.status = "resolved"
        cand.suggested_entity_id = row.id
        cand.match_reason = "steward_created_provisional_distributor"
        await db.commit()
        await db.refresh(row)
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create distributor or alias")
    return {"ok": True, "distributor_id": row.id, "distributor_code": row.code, "alias_id": alias.id, "candidate_id": cand.id}


async def _assert_dsi_import_job(db: AsyncSession, job_id: int) -> ImportJob:
    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    if (job.template_slug or "") != "distributor_inventory":
        raise HTTPException(status_code=400, detail="Job is not a distributor sales & inventory import")
    return job


class DsiBulkStewardBody(BaseModel):
    """Bulk steward preview/apply: same validation rules as single-row endpoints."""

    action: Literal["ignore", "map_customer", "map_distributor", "resolve_product"]
    candidate_ids: list[int] = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    customer_id: int | None = Field(default=None, ge=1)
    distributor_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)
    raw_token: str | None = Field(default=None, max_length=512)
    confirm_ineligible_product: bool = False
    audit_note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _payload_for_action(self) -> Self:
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


@router.post("/import-jobs/{job_id}/dsi-steward-bulk-apply", status_code=200)
async def dsi_steward_bulk_apply(job_id: int, body: DsiBulkStewardBody, db: AsyncSession = Depends(get_db)):
    await _assert_dsi_import_job(db, job_id)
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
            if body.action == "ignore":
                out = await execute_ignore_dsi_candidate(db, cand, notes=body.notes)
            elif body.action == "map_customer":
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


@router.post("/import-jobs/{job_id}/revalidate-distributor-sales-inventory", status_code=200)
async def revalidate_dsi_import_job(job_id: int, db: AsyncSession = Depends(get_db)):
    await _assert_dsi_import_job(db, job_id)

    def _run() -> ImportJob:
        with SessionLocal() as s:
            return process_import_job_sync(s, job_id)

    try:
        updated = await asyncio.to_thread(_run)
    except Exception as exc:  # pragma: no cover - surfaced to client
        raise HTTPException(status_code=500, detail=f"Revalidation failed: {exc}") from exc

    return {
        "ok": True,
        "import_job_id": updated.id,
        "status": updated.status,
        "stage": updated.stage,
        "template_slug": updated.template_slug,
    }


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
