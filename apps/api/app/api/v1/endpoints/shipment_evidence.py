"""Read APIs for canonical shipment / order evidence lines."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)
from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    _re_enrich_open_shipment_customer_candidates,
    execute_bulk_create_provisional_shipment_customers,
    execute_create_provisional_shipment_customer,
    execute_create_provisional_shipment_distributor,
    execute_manual_special_category_shipment_candidate,
    execute_map_shipment_customer,
    execute_map_shipment_distributor,
    execute_reject_shipment_mapping_candidate,
)

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


def _shipment_candidate_eligible_for_apply_auto_map(cand: ImportEntityMappingCandidate) -> bool:
    """Align with ``shipment_evidence_resolution_plan`` scoring for map paths.

    ``map_distributor`` / ``map_customer`` are only emitted with ``confidence_score`` of **1.0** or **0.95**;
    all other actions use lower scores. Require ``needs_review``, ``suggested_entity_id``, and entity/action match.
    """
    if cand.status != "needs_review":
        return False
    sc = cand.confidence_score
    if sc is None:
        return False
    try:
        score = float(sc)
    except (TypeError, ValueError):
        return False
    if score < 0.95:
        return False
    ctx = cand.context if isinstance(cand.context, dict) else {}
    action = (str(ctx.get("suggested_action") or "")).strip()
    if cand.suggested_entity_id is None:
        return False
    if action == "map_distributor":
        return cand.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY
    if action == "map_customer":
        return cand.entity_type == SHIPMENT_CUSTOMER_ENTITY
    return False


def _apply_high_confidence_shipment_mapping_candidates(import_job_id: int) -> int:
    """Execute ``execute_map_shipment_*`` for each eligible candidate; executors commit per call."""
    applied = 0
    with SessionLocal() as s:
        ids = [
            int(x)
            for x in s.scalars(
                select(ImportEntityMappingCandidate.id).where(
                    ImportEntityMappingCandidate.import_job_id == int(import_job_id),
                    ImportEntityMappingCandidate.entity_type.in_(
                        (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY)
                    ),
                    ImportEntityMappingCandidate.status == "needs_review",
                ).order_by(ImportEntityMappingCandidate.id)
            ).all()
        ]
        for cid in ids:
            cand = s.get(ImportEntityMappingCandidate, cid)
            if cand is None or not _shipment_candidate_eligible_for_apply_auto_map(cand):
                continue
            ctx = cand.context if isinstance(cand.context, dict) else {}
            action = (str(ctx.get("suggested_action") or "")).strip()
            eid = int(cand.suggested_entity_id)
            try:
                if action == "map_distributor":
                    execute_map_shipment_distributor(s, cand, distributor_id=eid, raw_token=None)
                    applied += 1
                elif action == "map_customer":
                    execute_map_shipment_customer(s, cand, customer_id=eid, raw_token=None)
                    applied += 1
            except ShipmentStewardOpError:
                continue
    return applied


def _is_admin(x_user_role: str | None) -> bool:
    return (x_user_role or "").strip().lower() == "admin"


def _require_admin(x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None) -> None:
    if not _is_admin(x_user_role):
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Requires X-User-Role: admin"},
        )


def _line_to_dict(
    row: ShipmentEvidenceLine,
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


def _apply_filters(stmt: Any, **kwargs: Any) -> Any:
    import_job_id = kwargs.get("import_job_id")
    line_state = kwargs.get("line_state")
    report_type = kwargs.get("report_type")
    product_resolution_status = kwargs.get("product_resolution_status")
    distributor_resolution_status = kwargs.get("distributor_resolution_status")
    search = kwargs.get("search")
    if import_job_id is not None:
        stmt = stmt.where(ShipmentEvidenceLine.import_job_id == import_job_id)
    if line_state:
        stmt = stmt.where(ShipmentEvidenceLine.line_state == line_state)
    if report_type:
        stmt = stmt.where(ShipmentEvidenceLine.report_type == report_type)
    if product_resolution_status:
        stmt = stmt.where(ShipmentEvidenceLine.product_resolution_status == product_resolution_status)
    if distributor_resolution_status:
        stmt = stmt.where(ShipmentEvidenceLine.distributor_resolution_status == distributor_resolution_status)
    if search and str(search).strip():
        term = f"%{str(search).strip()}%"
        stmt = stmt.where(
            or_(
                ShipmentEvidenceLine.bill_to_raw.ilike(term),
                ShipmentEvidenceLine.ship_to_raw.ilike(term),
                ShipmentEvidenceLine.customer_dealer_token.ilike(term),
                ShipmentEvidenceLine.item_code.ilike(term),
                ShipmentEvidenceLine.sales_model_name.ilike(term),
                ShipmentEvidenceLine.order_no.ilike(term),
                ShipmentEvidenceLine.delivery_no.ilike(term),
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
    sql = text(
        """
        SELECT DISTINCT jsonb_object_keys(raw_source_row) AS k
        FROM shipment_evidence_line
        WHERE import_job_id = :import_job_id
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


@router.post("/import-candidates/bulk-map-customer")
async def shipment_import_candidates_bulk_map_customer(
    body: ShipmentBulkMapCustomerBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Map many shipment customer candidates to one existing customer; re-enriches the job once at the end."""
    _require_admin(x_user_role)
    mapped: list[int] = []
    errors: list[dict[str, Any]] = []
    with SessionLocal() as s:
        job_id: int | None = None
        for cid in body.candidate_ids:
            cand = s.get(ImportEntityMappingCandidate, int(cid))
            if not cand or cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
                errors.append({"candidate_id": int(cid), "reason": "candidate_not_found_or_wrong_entity"})
                continue
            if job_id is None:
                job_id = int(cand.import_job_id)
            elif int(cand.import_job_id) != job_id:
                errors.append({"candidate_id": int(cid), "reason": "candidate_not_same_import_job"})
                continue
            try:
                execute_map_shipment_customer(s, cand, customer_id=body.customer_id, raw_token=None)
                mapped.append(int(cid))
            except ShipmentStewardOpError as exc:
                errors.append({"candidate_id": int(cid), "reason": str(exc.detail)})
        if mapped:
            any_cand = s.get(ImportEntityMappingCandidate, mapped[0])
            if any_cand is not None:
                _re_enrich_open_shipment_customer_candidates(s, any_cand)
            s.commit()
    return {"mapped": mapped, "errors": errors}


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


@router.post("/import-jobs/{job_id}/bulk-create-provisional-customers")
async def shipment_import_job_bulk_create_provisional_customers(
    job_id: int,
    body: ShipmentBulkProvisionalCustomersBody,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    per: dict[int, str] = {}
    if body.display_names:
        for k, v in body.display_names.items():
            try:
                per[int(k)] = v
            except (TypeError, ValueError):
                continue
    with SessionLocal() as s:
        out = execute_bulk_create_provisional_shipment_customers(
            s,
            job_id=job_id,
            candidate_ids=body.candidate_ids,
            per_candidate_display_name=per,
            region_id=body.region_id,
            channel_id=body.channel_id,
            preferred_distributor_id=body.preferred_distributor_id,
            partner_tier=body.partner_tier,
            notes_summary=body.notes_summary,
        )
    return out


@router.post("/jobs/{job_id}/apply")
async def apply_shipment_import_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Apply an inbound_shipments import job: auto-map planner-confident ``map_*`` candidates, then ``loaded``."""
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment import job not found")
    if job.stage == STAGE_LOADED:
        unresolved_d = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_DISTRIBUTOR_ENTITY)
        unresolved_c = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_CUSTOMER_ENTITY)
        return {
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
    auto_applied = _apply_high_confidence_shipment_mapping_candidates(job_id)
    job.stage = STAGE_LOADED
    job.status = "completed"
    await db.commit()
    await db.refresh(job)
    unresolved_d = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_DISTRIBUTOR_ENTITY)
    unresolved_c = await _unresolved_shipment_mapping_candidate_count(db, job_id, SHIPMENT_CUSTOMER_ENTITY)
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "template_slug": job.template_slug,
        "import_mode": job.import_mode,
        "unresolved_distributor_candidates": unresolved_d,
        "unresolved_customer_candidates": unresolved_c,
        "auto_applied_candidate_count": auto_applied,
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
    filt: dict[str, Any] = {
        "import_job_id": import_job_id,
        "line_state": line_state,
        "report_type": report_type,
        "product_resolution_status": product_resolution_status,
        "distributor_resolution_status": distributor_resolution_status,
        "search": search,
    }
    count_stmt = select(func.count()).select_from(ShipmentEvidenceLine)
    count_stmt = _apply_filters(count_stmt, **filt)
    total = int((await db.execute(count_stmt)).scalar_one())

    q = select(ShipmentEvidenceLine).order_by(ShipmentEvidenceLine.id.desc())
    q = _apply_filters(q, **filt)
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


@router.get("/{line_id}")
async def get_shipment_evidence_line(
    line_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    row = await db.get(ShipmentEvidenceLine, line_id)
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
