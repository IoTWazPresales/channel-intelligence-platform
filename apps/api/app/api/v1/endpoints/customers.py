from datetime import datetime, timezone
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_db
from app.api.v1.bulk_delete_sql_probe import apply_sql_probe_headers, bulk_delete_sql_probe
from app.models.dimensions import (
    CustomerContact,
    CustomerLocation,
    DimChannel,
    DimCustomer,
    DimDistributor,
    DimRegion,
)
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.ingestion import ImportJob
from app.services.customer_duplicate_groups import list_customer_duplicate_groups
from app.services.customer_usage import (
    cleanup_soft_customer_references,
    customer_hard_reference_breakdown,
    delete_customer_children,
)
from app.services.customer_location_usage import customer_location_hard_reference_breakdown
from app.api.v1.master_bulk_delete_http import raise_bulk_delete_http_error
from app.services.master_entity_bulk_delete import (
    MasterBulkDeleteConfirmBody,
    MasterBulkDeleteIntegrityError,
    confirm_master_bulk_delete,
    preview_master_bulk_delete,
)

router = APIRouter()


class MasterBulkIdsBody(BaseModel):
    entity_ids: list[int] = Field(default_factory=list, max_length=200)

ALLOWED_CUSTOMER_STATUS = {"active", "inactive", "onboarding", "blocked", "unverified", "needs_review"}
ALLOWED_PARTNER_TIER = {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail", "unmanaged"}
TMP_CUSTOMER_CODE_PREFIX = "TMP-CUST"
PROVISIONAL_REUSE_STATUS_WARNING = (
    "Leaving unverified stops provisional reuse for this row; future imports may mint a duplicate."
)
ALLOWED_LOCATION_TYPE = {"hq", "store", "warehouse", "branch", "online", "other"}
ALLOWED_CONTACT_ROLE = {"procurement", "sales", "operations", "finance", "support", "executive", "general"}


class CustomerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    customer_status: str | None = Field(default=None, max_length=32)
    partner_tier: str | None = Field(default=None, max_length=32)
    account_owner_internal: str | None = Field(default=None, max_length=128)
    notes_summary: str | None = Field(default=None, max_length=512)
    region_id: int | None = None
    channel_id: int | None = None
    preferred_distributor_id: int | None = None


class CustomerCreate(BaseModel):
    customer_code: str | None = Field(default=None, max_length=64)
    customer_name: str = Field(min_length=1, max_length=256)
    customer_status: str = Field(default="active", max_length=32)
    region_id: int
    channel_id: int
    partner_tier: str | None = Field(default=None, max_length=32)
    account_owner_internal: str | None = Field(default=None, max_length=128)
    notes_summary: str | None = Field(default=None, max_length=512)
    preferred_distributor_id: int | None = None


class CustomerBulkRow(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    region_code: str | None = Field(default=None, max_length=32)
    channel_code: str | None = Field(default=None, max_length=32)


class CustomerBulkBody(BaseModel):
    rows: list[CustomerBulkRow]


class CustomerPromoteBody(BaseModel):
    new_code: str = Field(min_length=1, max_length=64)
    confirm: bool = False
    note: str | None = Field(default=None, max_length=512)


class CustomerBulkPromoteRow(BaseModel):
    tmp_code: str = Field(min_length=0, max_length=64)
    new_code: str = Field(default="", max_length=64)
    note: str | None = Field(default=None, max_length=512)


class CustomerBulkPromoteBody(BaseModel):
    rows: list[CustomerBulkPromoteRow]
    dry_run: bool = True


class CustomerLocationCreate(BaseModel):
    location_code: str = Field(min_length=1, max_length=64)
    location_name: str = Field(min_length=1, max_length=256)
    location_type: str = Field(default="store", max_length=32)
    region_id: int | None = None
    is_active: bool = True
    notes_summary: str | None = Field(default=None, max_length=512)


class CustomerLocationPatch(BaseModel):
    location_code: str | None = Field(default=None, min_length=1, max_length=64)
    location_name: str | None = Field(default=None, min_length=1, max_length=256)
    location_type: str | None = Field(default=None, max_length=32)
    region_id: int | None = None
    is_active: bool | None = None
    notes_summary: str | None = Field(default=None, max_length=512)


class CustomerContactCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=256)
    contact_role: str = Field(default="general", max_length=32)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    is_primary: bool = False
    is_active: bool = True
    notes_summary: str | None = Field(default=None, max_length=512)


class CustomerContactPatch(BaseModel):
    contact_name: str | None = Field(default=None, min_length=1, max_length=256)
    contact_role: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    is_primary: bool | None = None
    is_active: bool | None = None
    notes_summary: str | None = Field(default=None, max_length=512)


def _normalize_customer_status(raw_value: str | None) -> str:
    raw = (raw_value or "").strip().lower()
    if raw not in ALLOWED_CUSTOMER_STATUS:
        raise HTTPException(status_code=400, detail="Invalid customer_status")
    return raw


def _provisional_reuse_status_warning(row: DimCustomer, new_status: str | None) -> str | None:
    """Warn when a TMP-CUST provisional leaves ``unverified`` (stops reuse; may duplicate)."""
    if new_status is None:
        return None
    prior = (row.customer_status or "").strip().lower()
    if prior != "unverified":
        return None
    if new_status.strip().lower() == "unverified":
        return None
    code = (row.code or "").strip()
    if not code.startswith(f"{TMP_CUSTOMER_CODE_PREFIX}-"):
        return None
    return PROVISIONAL_REUSE_STATUS_WARNING


def _normalize_partner_tier(raw_value: str | None) -> str | None:
    raw = (raw_value or "").strip().lower()
    if raw and raw not in ALLOWED_PARTNER_TIER:
        raise HTTPException(status_code=400, detail="Invalid partner_tier")
    return raw or None


def _normalize_location_type(raw_value: str | None) -> str:
    raw = (raw_value or "").strip().lower()
    if raw not in ALLOWED_LOCATION_TYPE:
        raise HTTPException(status_code=400, detail="Invalid location_type")
    return raw


def _normalize_contact_role(raw_value: str | None) -> str:
    raw = (raw_value or "").strip().lower()
    if raw not in ALLOWED_CONTACT_ROLE:
        raise HTTPException(status_code=400, detail="Invalid contact_role")
    return raw


def _location_to_api(row: CustomerLocation, region_code: str | None) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "location_code": row.location_code,
        "location_name": row.location_name,
        "location_type": row.location_type,
        "region_id": row.region_id,
        "region_code": region_code,
        "is_active": row.is_active,
        "notes_summary": row.notes_summary,
    }


def _contact_to_api(row: CustomerContact) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "contact_name": row.contact_name,
        "contact_role": row.contact_role,
        "email": row.email,
        "phone": row.phone,
        "is_primary": row.is_primary,
        "is_active": row.is_active,
        "notes_summary": row.notes_summary,
    }


async def _generate_tmp_customer_code(db: AsyncSession) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _ in range(8):
        candidate = f"{TMP_CUSTOMER_CODE_PREFIX}-{stamp}-{secrets.token_hex(2).upper()}"
        exists = await db.execute(select(DimCustomer.id).where(DimCustomer.code == candidate))
        if exists.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(
        status_code=503,
        detail="Unable to generate a temporary customer_code; retry create operation.",
    )


@router.get("")
async def list_customers(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, description="Global search over customer identity"),
    customer_status: str | None = Query(default=None),
    status: str | None = Query(default=None, description="Alias for customer_status (e.g. unverified)"),
    job_id: int | None = Query(
        default=None,
        ge=1,
        description="Restrict to customers whose notes reference this import job (e.g. provisionals from steward)",
    ),
    customer_id: int | None = Query(default=None, ge=1, description="When set, return at most this customer id"),
    partner_tier: str | None = Query(default=None),
    region_code: str | None = Query(default=None),
    channel_code: str | None = Query(default=None),
    preferred_distributor_code: str | None = Query(default=None),
    min_alias_count: int | None = Query(default=None, ge=0, description="Minimum approved source-token alias count"),
    alias_link: str | None = Query(
        default=None,
        description="Filter by alias linkage: linked (≥1 alias) or unlinked (0 aliases)",
    ),
    is_key_account: bool | None = Query(
        default=None,
        description="When true, only key-account customers; when false, only non-key; omit for all",
    ),
    sort_by: str = Query(default="code"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    pref_dist = aliased(DimDistributor)
    location_count_sq = (
        select(func.count())
        .select_from(CustomerLocation)
        .where(CustomerLocation.customer_id == DimCustomer.id)
        .correlate(DimCustomer)
        .scalar_subquery()
    )
    contact_count_sq = (
        select(func.count())
        .select_from(CustomerContact)
        .where(CustomerContact.customer_id == DimCustomer.id)
        .correlate(DimCustomer)
        .scalar_subquery()
    )
    alias_count_sq = (
        select(func.count())
        .select_from(CustomerSourceTokenAlias)
        .where(
            CustomerSourceTokenAlias.customer_id == DimCustomer.id,
            CustomerSourceTokenAlias.status == "approved",
        )
        .correlate(DimCustomer)
        .scalar_subquery()
    )
    last_import_from_alias_sq = (
        select(func.max(ImportJob.created_at))
        .select_from(CustomerSourceTokenAlias)
        .join(ImportJob, ImportJob.id == CustomerSourceTokenAlias.created_from_import_job_id)
        .where(CustomerSourceTokenAlias.customer_id == DimCustomer.id)
        .correlate(DimCustomer)
        .scalar_subquery()
    )
    allowed_sort = {
        "id": DimCustomer.id,
        "code": DimCustomer.code,
        "name": DimCustomer.name,
        "customer_status": DimCustomer.customer_status,
        "partner_tier": DimCustomer.partner_tier,
        "account_owner_internal": DimCustomer.account_owner_internal,
        "region_id": DimCustomer.region_id,
        "channel_id": DimCustomer.channel_id,
        "preferred_distributor_id": DimCustomer.preferred_distributor_id,
        "created_at": DimCustomer.created_at,
        "updated_at": DimCustomer.updated_at,
        "region_code": DimRegion.code,
        "channel_code": DimChannel.code,
        "preferred_distributor_code": pref_dist.code,
        "alias_count": alias_count_sq,
        "last_import_at": last_import_from_alias_sq,
        "location_count": location_count_sq,
        "contact_count": contact_count_sq,
    }
    sort_col = allowed_sort.get(sort_by, DimCustomer.code)
    sort_fn = asc if sort_dir == "asc" else desc

    base = (
        select(
            DimCustomer,
            DimRegion.code.label("region_code"),
            DimChannel.code.label("channel_code"),
            pref_dist.code.label("preferred_distributor_code"),
            pref_dist.name.label("preferred_distributor_name"),
            location_count_sq.label("location_count"),
            contact_count_sq.label("contact_count"),
            alias_count_sq.label("alias_count"),
            last_import_from_alias_sq.label("last_import_at"),
        )
        .join(DimRegion, DimRegion.id == DimCustomer.region_id, isouter=True)
        .join(DimChannel, DimChannel.id == DimCustomer.channel_id, isouter=True)
        .join(pref_dist, pref_dist.id == DimCustomer.preferred_distributor_id, isouter=True)
    )

    filters = []
    if q and q.strip():
        needle = f"%{q.strip()}%"
        filters.append(
            or_(
                DimCustomer.code.ilike(needle),
                DimCustomer.name.ilike(needle),
                DimCustomer.account_owner_internal.ilike(needle),
                DimCustomer.notes_summary.ilike(needle),
            )
        )

    eff_status = (customer_status or status or "").strip()
    if eff_status:
        filters.append(DimCustomer.customer_status == eff_status.lower())

    if job_id is not None:
        filters.append(DimCustomer.notes_summary.ilike(f"%(job {int(job_id)})%"))

    if customer_id is not None:
        filters.append(DimCustomer.id == int(customer_id))

    if partner_tier and partner_tier.strip():
        pt = partner_tier.strip().lower()
        filters.append(DimCustomer.partner_tier == pt)

    if region_code and region_code.strip():
        rc = region_code.strip()
        base = base.where(DimRegion.code == rc)

    if channel_code and channel_code.strip():
        cc = channel_code.strip()
        base = base.where(DimChannel.code == cc)

    if preferred_distributor_code and preferred_distributor_code.strip():
        pdc = preferred_distributor_code.strip()
        base = base.where(pref_dist.code == pdc)

    if min_alias_count is not None:
        base = base.where(alias_count_sq >= int(min_alias_count))

    al = (alias_link or "").strip().lower()
    if al == "linked":
        base = base.where(alias_count_sq > 0)
    elif al == "unlinked":
        base = base.where(alias_count_sq == 0)

    if is_key_account is not None:
        filters.append(DimCustomer.is_key_account.is_(bool(is_key_account)))

    if filters:
        base = base.where(and_(*filters))

    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    offset = (page - 1) * page_size
    if job_id is not None and not (q and q.strip()):
        order_parts = (desc(DimCustomer.created_at), asc(DimCustomer.id))
    elif q and q.strip():
        order_parts = (
            case((DimCustomer.customer_status == "unverified", 0), else_=1).asc(),
            desc(DimCustomer.updated_at),
            sort_fn(sort_col),
            asc(DimCustomer.id),
        )
    else:
        order_parts = (sort_fn(sort_col), asc(DimCustomer.id))
    rows = (await db.execute(base.order_by(*order_parts).offset(offset).limit(page_size))).all()

    items = []
    for row in rows:
        (
            c,
            region_code_out,
            channel_code_out,
            pref_code,
            pref_name,
            location_count,
            contact_count,
            alias_count,
            last_import_at,
        ) = row
        n_aliases = int(alias_count or 0)
        items.append(
            {
                "id": c.id,
                "customer_code": c.code,
                "customer_name": c.name,
                "customer_status": c.customer_status,
                "is_key_account": bool(c.is_key_account),
                "created_at": c.created_at.isoformat() if c.created_at is not None else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at is not None else None,
                "partner_tier": c.partner_tier,
                "account_owner_internal": c.account_owner_internal,
                "notes_summary": c.notes_summary,
                "region_id": c.region_id,
                "channel_id": c.channel_id,
                "preferred_distributor_id": c.preferred_distributor_id,
                "region_code": region_code_out,
                "channel_code": channel_code_out,
                "preferred_distributor_code": pref_code,
                "preferred_distributor_name": pref_name,
                "location_count": int(location_count or 0),
                "contact_count": int(contact_count or 0),
                "alias_count": n_aliases,
                "last_import_at": last_import_at.isoformat() if last_import_at is not None else None,
                "alias_link_status": "linked" if n_aliases > 0 else "unlinked",
            }
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "sort_by": sort_by if sort_by in allowed_sort else "code",
        "sort_dir": sort_dir,
    }


@router.get("/duplicate-groups")
async def list_customer_duplicate_groups_endpoint(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    """Read-only: groups of customers sharing a similarity-normalised name key (2+ members)."""
    return await list_customer_duplicate_groups(db, page=page, page_size=page_size)


class CustomerAliasScopeMergeBody(BaseModel):
    normalized_token: str = Field(min_length=1, max_length=512)
    source_definition_id: int | None = None
    distributor_id: int | None = None
    survivor_id: int | None = None
    audit_note: str = Field(min_length=1, max_length=2000)
    return_import_job_id: int | None = None


@router.get("/alias-scope-conflicts")
async def list_customer_alias_scope_conflicts_endpoint(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    normalized_token: str | None = Query(default=None),
):
    from app.services.customer_alias_scope_conflicts import list_customer_alias_scope_conflicts

    return await list_customer_alias_scope_conflicts(
        db,
        page=page,
        page_size=page_size,
        normalized_token=normalized_token,
    )


@router.post("/alias-scope-conflicts/merge-preview")
async def customer_alias_scope_merge_preview_endpoint(body: CustomerAliasScopeMergeBody):
    import asyncio

    from app.db.session_sync import SessionLocal
    from app.services.customer_alias_scope_merge import (
        CustomerAliasScopeMergeError,
        preview_customer_alias_scope_merge,
    )

    def _run() -> dict:
        with SessionLocal() as db:
            return preview_customer_alias_scope_merge(
                db,
                normalized_token=body.normalized_token,
                source_definition_id=body.source_definition_id,
                distributor_id=body.distributor_id,
                survivor_id=body.survivor_id,
                audit_note=body.audit_note,
            )

    try:
        return await asyncio.to_thread(_run)
    except CustomerAliasScopeMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/alias-scope-conflicts/merge-confirm", status_code=202)
async def customer_alias_scope_merge_confirm_endpoint(body: CustomerAliasScopeMergeBody):
    from app.services.customer_alias_scope_merge import CustomerAliasScopeMergeError
    from app.services.customer_alias_scope_merge_enqueue import enqueue_customer_alias_scope_merge_confirm

    if body.survivor_id is None:
        raise HTTPException(status_code=400, detail="survivor_id is required for merge-confirm")

    payload = {
        "normalized_token": body.normalized_token,
        "source_definition_id": body.source_definition_id,
        "distributor_id": body.distributor_id,
        "survivor_id": int(body.survivor_id),
        "audit_note": body.audit_note,
        "return_import_job_id": body.return_import_job_id,
    }
    try:
        task_id, async_poll = enqueue_customer_alias_scope_merge_confirm(payload)
    except CustomerAliasScopeMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    out: dict = {
        "task_id": task_id,
        "async_poll": async_poll,
        "scope": {
            "normalized_token": body.normalized_token,
            "source_definition_id": body.source_definition_id,
            "distributor_id": body.distributor_id,
        },
        "survivor_id": body.survivor_id,
    }
    if body.return_import_job_id is not None:
        out["revalidate_import_job_id"] = body.return_import_job_id
        out["revalidate_href"] = f"/admin/imports?job={body.return_import_job_id}"
    return out


@router.get("/alias-scope-conflicts/merge-task/{task_id}")
async def customer_alias_scope_merge_task_status(task_id: str):
    import asyncio

    from app.services.customer_alias_scope_merge_enqueue import dev_customer_alias_scope_merge_results
    from app.services.task_run_ledger import (
        POLL_STATE_FAILURE,
        POLL_STATE_SUCCESS,
        read_task_run_poll_progress_sync,
    )

    dev_hit = dev_customer_alias_scope_merge_results().get(task_id)
    if dev_hit is not None:
        state = dev_hit.get("state", POLL_STATE_SUCCESS)
        if state in (POLL_STATE_SUCCESS, POLL_STATE_FAILURE):
            dev_customer_alias_scope_merge_results().pop(task_id, None)
        progress: dict = {"task_id": task_id, "state": state}
        if state == POLL_STATE_SUCCESS:
            progress["result"] = dev_hit.get("result")
        else:
            progress["error"] = dev_hit.get("error")
        return progress

    ledger_progress = await asyncio.to_thread(read_task_run_poll_progress_sync, task_id)
    if ledger_progress is not None:
        return ledger_progress

    from celery.result import AsyncResult

    from app.worker.celery_app import celery_app

    def _read() -> tuple[str, Any]:
        r = AsyncResult(task_id, app=celery_app)
        return r.state, r.info

    task_state, info = await asyncio.to_thread(_read)
    progress = {"task_id": task_id, "state": task_state}
    if task_state == POLL_STATE_SUCCESS:
        from celery.result import AsyncResult as _AR

        raw_result = await asyncio.to_thread(lambda: _AR(task_id, app=celery_app).result)
        progress["result"] = raw_result if isinstance(raw_result, dict) else None
    elif task_state == POLL_STATE_FAILURE:
        progress["error"] = str(info)[:800] if info is not None else "Task failed"
    return progress


class CustomerFullMergeBody(BaseModel):
    similarity_key: str = Field(min_length=1, max_length=512)
    survivor_id: int | None = None
    customer_ids: list[int] | None = None
    audit_note: str = Field(min_length=1, max_length=2000)


class CustomerFullMergeBulkPreviewBody(BaseModel):
    groups: list[dict[str, Any]]
    audit_note: str = Field(min_length=1, max_length=2000)


@router.post("/duplicate-groups/merge-preview")
async def customer_full_merge_preview_endpoint(body: CustomerFullMergeBody):
    import asyncio

    from app.db.session_sync import SessionLocal
    from app.services.customer_full_merge import CustomerFullMergeError, preview_customer_full_merge

    def _run() -> dict:
        with SessionLocal() as db:
            return preview_customer_full_merge(
                db,
                similarity_key=body.similarity_key,
                survivor_id=body.survivor_id,
                audit_note=body.audit_note,
                customer_ids=body.customer_ids,
            )

    try:
        return await asyncio.to_thread(_run)
    except CustomerFullMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/duplicate-groups/merge-preview-bulk")
async def customer_full_merge_bulk_preview_endpoint(body: CustomerFullMergeBulkPreviewBody):
    import asyncio

    from app.db.session_sync import SessionLocal
    from app.services.customer_full_merge import CustomerFullMergeError, preview_customer_full_merge_bulk

    def _run() -> dict:
        with SessionLocal() as db:
            return preview_customer_full_merge_bulk(
                db,
                groups=body.groups,
                audit_note=body.audit_note,
            )

    try:
        return await asyncio.to_thread(_run)
    except CustomerFullMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/duplicate-groups/merge-confirm", status_code=202)
async def customer_full_merge_confirm_endpoint(body: CustomerFullMergeBody):
    from app.services.customer_full_merge import CustomerFullMergeError
    from app.services.customer_full_merge_enqueue import enqueue_customer_full_merge_confirm

    if body.survivor_id is None:
        raise HTTPException(status_code=400, detail="survivor_id is required for merge-confirm")

    payload = {
        "similarity_key": body.similarity_key,
        "survivor_id": int(body.survivor_id),
        "audit_note": body.audit_note,
        "customer_ids": body.customer_ids,
    }
    try:
        task_id, async_poll = enqueue_customer_full_merge_confirm(payload)
    except CustomerFullMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "task_id": task_id,
        "async_poll": async_poll,
        "similarity_key": body.similarity_key,
        "survivor_id": body.survivor_id,
    }


@router.get("/duplicate-groups/merge-task/{task_id}")
async def customer_full_merge_task_status(task_id: str):
    import asyncio

    from app.services.customer_full_merge_enqueue import dev_customer_full_merge_results
    from app.services.task_run_ledger import (
        POLL_STATE_FAILURE,
        POLL_STATE_SUCCESS,
        read_task_run_poll_progress_sync,
    )

    dev_hit = dev_customer_full_merge_results().get(task_id)
    if dev_hit is not None:
        state = dev_hit.get("state", POLL_STATE_SUCCESS)
        if state in (POLL_STATE_SUCCESS, POLL_STATE_FAILURE):
            dev_customer_full_merge_results().pop(task_id, None)
        progress: dict = {"task_id": task_id, "state": state}
        if state == POLL_STATE_SUCCESS:
            progress["result"] = dev_hit.get("result")
        else:
            progress["error"] = dev_hit.get("error")
        return progress

    ledger_progress = await asyncio.to_thread(read_task_run_poll_progress_sync, task_id)
    if ledger_progress is not None:
        return ledger_progress

    from celery.result import AsyncResult

    from app.worker.celery_app import celery_app

    def _read() -> tuple[str, Any]:
        r = AsyncResult(task_id, app=celery_app)
        return r.state, r.info

    task_state, info = await asyncio.to_thread(_read)
    progress = {"task_id": task_id, "state": task_state}
    if task_state == POLL_STATE_SUCCESS:
        from celery.result import AsyncResult as _AR

        raw_result = await asyncio.to_thread(lambda: _AR(task_id, app=celery_app).result)
        progress["result"] = raw_result if isinstance(raw_result, dict) else None
    elif task_state == POLL_STATE_FAILURE:
        progress["error"] = str(info)[:800] if info is not None else "Task failed"
    return progress


@router.post("", status_code=201)
async def create_customer(body: CustomerCreate, db: AsyncSession = Depends(get_db)):
    customer_name = body.customer_name.strip()
    if not customer_name:
        raise HTTPException(status_code=400, detail="customer_name is required")
    customer_status = _normalize_customer_status(body.customer_status)
    partner_tier = _normalize_partner_tier(body.partner_tier)

    region = await db.get(DimRegion, body.region_id)
    if not region:
        raise HTTPException(status_code=400, detail="Invalid region_id")
    channel = await db.get(DimChannel, body.channel_id)
    if not channel:
        raise HTTPException(status_code=400, detail="Invalid channel_id")
    preferred_distributor = None
    if body.preferred_distributor_id is not None:
        preferred_distributor = await db.get(DimDistributor, body.preferred_distributor_id)
        if not preferred_distributor:
            raise HTTPException(status_code=400, detail="Invalid preferred_distributor_id")

    requested_code = (body.customer_code or "").strip()
    customer_code = requested_code or await _generate_tmp_customer_code(db)

    row = DimCustomer(
        code=customer_code,
        name=customer_name,
        customer_status=customer_status,
        partner_tier=partner_tier,
        account_owner_internal=(body.account_owner_internal or "").strip() or None,
        notes_summary=(body.notes_summary or "").strip() or None,
        region_id=body.region_id,
        channel_id=body.channel_id,
        preferred_distributor_id=body.preferred_distributor_id,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="customer_code already exists; provide a unique code or leave blank for a temporary code.",
        ) from None

    await db.refresh(row)
    return {
        "id": row.id,
        "customer_code": row.code,
        "customer_name": row.name,
        "customer_status": row.customer_status,
        "partner_tier": row.partner_tier,
        "account_owner_internal": row.account_owner_internal,
        "notes_summary": row.notes_summary,
        "region_id": row.region_id,
        "channel_id": row.channel_id,
        "preferred_distributor_id": row.preferred_distributor_id,
        "region_code": region.code,
        "channel_code": channel.code,
        "preferred_distributor_code": preferred_distributor.code if preferred_distributor else None,
        "preferred_distributor_name": preferred_distributor.name if preferred_distributor else None,
    }


@router.post("/bulk-delete-preview")
async def post_customers_bulk_delete_preview(
    body: MasterBulkIdsBody,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid customer id."},
        )
    with bulk_delete_sql_probe() as counter:
        payload = await preview_master_bulk_delete(db, "customers", body.entity_ids)
    apply_sql_probe_headers(response, counter)
    return payload


@router.post("/bulk-delete-confirm")
async def post_customers_bulk_delete_confirm(
    body: MasterBulkDeleteConfirmBody,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid customer id."},
        )
    try:
        with bulk_delete_sql_probe() as counter:
            payload = await confirm_master_bulk_delete(
                db,
                "customers",
                body.entity_ids,
                deletable_ids=body.deletable_ids,
            )
        apply_sql_probe_headers(response, counter)
        return payload
    except Exception as exc:
        raise_bulk_delete_http_error(exc, entity_label="customer")


@router.patch("/{customer_id}")
async def patch_customer(customer_id: int, body: CustomerPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimCustomer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    status_warning = _provisional_reuse_status_warning(
        row, data.get("customer_status") if "customer_status" in data else None
    )
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "customer_status" in data:
        row.customer_status = _normalize_customer_status(data["customer_status"])
    if "partner_tier" in data:
        row.partner_tier = _normalize_partner_tier(data["partner_tier"])
    if "account_owner_internal" in data:
        row.account_owner_internal = (data["account_owner_internal"] or "").strip() or None
    if "notes_summary" in data:
        row.notes_summary = (data["notes_summary"] or "").strip() or None
    if "region_id" in data:
        rid = data["region_id"]
        if rid is not None:
            reg = await db.get(DimRegion, rid)
            if not reg:
                raise HTTPException(status_code=400, detail="Invalid region_id")
        row.region_id = rid
    if "channel_id" in data:
        cid = data["channel_id"]
        if cid is not None:
            ch = await db.get(DimChannel, cid)
            if not ch:
                raise HTTPException(status_code=400, detail="Invalid channel_id")
        row.channel_id = cid
    if "preferred_distributor_id" in data:
        did = data["preferred_distributor_id"]
        if did is not None:
            dist = await db.get(DimDistributor, did)
            if not dist:
                raise HTTPException(status_code=400, detail="Invalid preferred_distributor_id")
        row.preferred_distributor_id = did
    await db.commit()
    await db.refresh(row)
    payload = {
        "id": row.id,
        "customer_code": row.code,
        "customer_name": row.name,
        "customer_status": row.customer_status,
        "partner_tier": row.partner_tier,
        "account_owner_internal": row.account_owner_internal,
        "notes_summary": row.notes_summary,
        "region_id": row.region_id,
        "channel_id": row.channel_id,
        "preferred_distributor_id": row.preferred_distributor_id,
    }
    if status_warning:
        payload["warnings"] = [status_warning]
    return payload


@router.post("/promote/batch")
async def promote_customers_batch(
    body: CustomerBulkPromoteBody,
    db: AsyncSession = Depends(get_db),
):
    """BACKLOG-061 BP1 — bulk promote via tmp_code→new_code mapping (CSV/paste).

    ``dry_run=true``: preview only. ``dry_run=false``: apply ready rows with partial
    success (per-row commit). Cap 500. No mint path. Never auto-creates dim_customer.
    """
    from app.services.customer_bulk_promote import BATCH_MAX_ROWS, run_customer_bulk_promote
    from app.services.customer_promote import CustomerPromoteError

    if len(body.rows) > BATCH_MAX_ROWS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Too many rows (max {BATCH_MAX_ROWS})",
                "code": "batch_too_large",
            },
        )
    try:
        return await run_customer_bulk_promote(
            db,
            rows=[r.model_dump() for r in body.rows],
            dry_run=body.dry_run,
        )
    except CustomerPromoteError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": exc.message, "code": exc.code},
        ) from exc


@router.post("/{customer_id}/promote")
async def promote_customer(
    customer_id: int,
    body: CustomerPromoteBody,
    db: AsyncSession = Depends(get_db),
):
    """BACKLOG-061 B1 — promote-in-place: same id, reassign TMP code → real code.

    Preview when ``confirm=false`` (no writes). Confirm requires ``confirm=true``.
    Never auto-creates dim_customer; never touches merged_into_* / aliases / FKs.
    """
    from app.services.customer_promote import (
        CustomerPromoteError,
        confirm_customer_promote,
        preview_customer_promote,
    )

    try:
        if not body.confirm:
            return await preview_customer_promote(
                db, customer_id=customer_id, new_code=body.new_code
            )
        return await confirm_customer_promote(
            db,
            customer_id=customer_id,
            new_code=body.new_code,
            note=body.note,
        )
    except CustomerPromoteError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": exc.message, "code": exc.code},
        ) from exc


@router.post("/bulk", status_code=200)
async def bulk_upsert_customers(body: CustomerBulkBody, db: AsyncSession = Depends(get_db)):
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    regions = {r.code: r.id for r in (await db.execute(select(DimRegion))).scalars().all()}
    channels = {c.code: c.id for c in (await db.execute(select(DimChannel))).scalars().all()}
    created = 0
    updated = 0
    for r in body.rows:
        code = r.code.strip()
        name = r.name.strip()
        region_id = None
        if r.region_code and r.region_code.strip():
            region_id = regions.get(r.region_code.strip())
            if region_id is None:
                raise HTTPException(status_code=400, detail=f"Unknown region_code for row {code!r}")
        channel_id = None
        if r.channel_code and r.channel_code.strip():
            channel_id = channels.get(r.channel_code.strip())
            if channel_id is None:
                raise HTTPException(status_code=400, detail=f"Unknown channel_code for row {code!r}")
        existing = await db.execute(select(DimCustomer).where(DimCustomer.code == code))
        row = existing.scalar_one_or_none()
        if row:
            row.name = name
            row.region_id = region_id
            row.channel_id = channel_id
            updated += 1
        else:
            db.add(
                DimCustomer(
                    code=code,
                    name=name,
                    customer_status="active",
                    region_id=region_id,
                    channel_id=channel_id,
                )
            )
            created += 1
    await db.commit()
    return {"created": created, "updated": updated, "total": len(body.rows)}


@router.get("/{customer_id}/locations")
async def list_customer_locations(customer_id: int, db: AsyncSession = Depends(get_db)):
    customer = await db.get(DimCustomer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Not found")
    rows = (
        await db.execute(
            select(CustomerLocation, DimRegion.code.label("region_code"))
            .join(DimRegion, DimRegion.id == CustomerLocation.region_id, isouter=True)
            .where(CustomerLocation.customer_id == customer_id)
            .order_by(CustomerLocation.location_code.asc(), CustomerLocation.id.asc())
        )
    ).all()
    return [_location_to_api(loc, region_code) for loc, region_code in rows]


@router.post("/{customer_id}/locations", status_code=201)
async def create_customer_location(
    customer_id: int, body: CustomerLocationCreate, db: AsyncSession = Depends(get_db)
):
    customer = await db.get(DimCustomer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Not found")
    region_code = None
    if body.region_id is not None:
        region = await db.get(DimRegion, body.region_id)
        if not region:
            raise HTTPException(status_code=400, detail="Invalid region_id")
        region_code = region.code
    row = CustomerLocation(
        customer_id=customer_id,
        location_code=body.location_code.strip(),
        location_name=body.location_name.strip(),
        location_type=_normalize_location_type(body.location_type),
        region_id=body.region_id,
        is_active=body.is_active,
        notes_summary=(body.notes_summary or "").strip() or None,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="location_code already exists for this customer",
        ) from None
    await db.refresh(row)
    return _location_to_api(row, region_code)


@router.patch("/{customer_id}/locations/{location_id}")
async def patch_customer_location(
    customer_id: int,
    location_id: int,
    body: CustomerLocationPatch,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(CustomerLocation, location_id)
    if not row or row.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "location_code" in data and data["location_code"] is not None:
        row.location_code = data["location_code"].strip()
    if "location_name" in data and data["location_name"] is not None:
        row.location_name = data["location_name"].strip()
    if "location_type" in data and data["location_type"] is not None:
        row.location_type = _normalize_location_type(data["location_type"])
    if "region_id" in data:
        rid = data["region_id"]
        if rid is not None:
            region = await db.get(DimRegion, rid)
            if not region:
                raise HTTPException(status_code=400, detail="Invalid region_id")
        row.region_id = rid
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = bool(data["is_active"])
    if "notes_summary" in data:
        row.notes_summary = (data["notes_summary"] or "").strip() or None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="location_code already exists for this customer",
        ) from None
    await db.refresh(row)
    region_code = None
    if row.region_id is not None:
        region = await db.get(DimRegion, row.region_id)
        region_code = region.code if region else None
    return _location_to_api(row, region_code)


async def _customer_references_bundle(db: AsyncSession, customer_id: int) -> dict:
    row = await db.get(DimCustomer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "customer_not_found", "customer_id": customer_id})
    refs = await customer_hard_reference_breakdown(db, customer_id)
    return {"customer_code": row.code, "references": refs, "blocked": len(refs) > 0}


@router.get("/references")
async def get_customer_references_by_query(
    customer_id: int = Query(..., ge=1, description="dim_customer.id"),
    db: AsyncSession = Depends(get_db),
):
    return await _customer_references_bundle(db, customer_id)


@router.get("/id/{customer_id}/refs")
async def get_customer_refs_for_delete_ux(customer_id: int, db: AsyncSession = Depends(get_db)):
    return await _customer_references_bundle(db, customer_id)


@router.get("/{customer_id}/references")
async def get_customer_references(customer_id: int, db: AsyncSession = Depends(get_db)):
    return await _customer_references_bundle(db, customer_id)


@router.delete("/{customer_id}/locations/{location_id}", status_code=204)
async def delete_customer_location(customer_id: int, location_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CustomerLocation, location_id)
    if not row or row.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Not found")
    refs = await customer_location_hard_reference_breakdown(db, location_id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Customer location is still referenced; remove dependent rows first.",
                "references": refs,
            },
        )
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs2 = await customer_location_hard_reference_breakdown(db, location_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Customer location could not be deleted (database constraint).",
                "references": refs2
                if refs2
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)


@router.get("/{customer_id}/contacts")
async def list_customer_contacts(customer_id: int, db: AsyncSession = Depends(get_db)):
    customer = await db.get(DimCustomer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Not found")
    rows = (
        await db.execute(
            select(CustomerContact)
            .where(CustomerContact.customer_id == customer_id)
            .order_by(CustomerContact.is_primary.desc(), CustomerContact.contact_name.asc(), CustomerContact.id.asc())
        )
    ).scalars().all()
    return [_contact_to_api(row) for row in rows]


@router.post("/{customer_id}/contacts", status_code=201)
async def create_customer_contact(
    customer_id: int, body: CustomerContactCreate, db: AsyncSession = Depends(get_db)
):
    customer = await db.get(DimCustomer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Not found")
    if body.is_primary:
        rows = (
            await db.execute(
                select(CustomerContact).where(
                    CustomerContact.customer_id == customer_id,
                    CustomerContact.is_primary.is_(True),
                )
            )
        ).scalars().all()
        for row in rows:
            row.is_primary = False
    row = CustomerContact(
        customer_id=customer_id,
        contact_name=body.contact_name.strip(),
        contact_role=_normalize_contact_role(body.contact_role),
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        is_primary=body.is_primary,
        is_active=body.is_active,
        notes_summary=(body.notes_summary or "").strip() or None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _contact_to_api(row)


@router.patch("/{customer_id}/contacts/{contact_id}")
async def patch_customer_contact(
    customer_id: int,
    contact_id: int,
    body: CustomerContactPatch,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(CustomerContact, contact_id)
    if not row or row.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "contact_name" in data and data["contact_name"] is not None:
        row.contact_name = data["contact_name"].strip()
    if "contact_role" in data and data["contact_role"] is not None:
        row.contact_role = _normalize_contact_role(data["contact_role"])
    if "email" in data:
        row.email = (data["email"] or "").strip() or None
    if "phone" in data:
        row.phone = (data["phone"] or "").strip() or None
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = bool(data["is_active"])
    if "notes_summary" in data:
        row.notes_summary = (data["notes_summary"] or "").strip() or None
    if "is_primary" in data and data["is_primary"] is not None:
        if bool(data["is_primary"]):
            rows = (
                await db.execute(
                    select(CustomerContact).where(
                        CustomerContact.customer_id == customer_id,
                        CustomerContact.is_primary.is_(True),
                        CustomerContact.id != row.id,
                    )
                )
            ).scalars().all()
            for other in rows:
                other.is_primary = False
            row.is_primary = True
        else:
            row.is_primary = False
    await db.commit()
    await db.refresh(row)
    return _contact_to_api(row)


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=204)
async def delete_customer_contact(customer_id: int, contact_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CustomerContact, contact_id)
    if not row or row.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimCustomer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    refs = await customer_hard_reference_breakdown(db, customer_id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Customer is still referenced; remove or clear dependent rows first.",
                "references": refs,
            },
        )
    await cleanup_soft_customer_references(db, customer_id)
    await delete_customer_children(db, customer_id)
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs2 = await customer_hard_reference_breakdown(db, customer_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Customer could not be deleted (database constraint). Dependent data may have changed.",
                "references": refs2
                if refs2
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)
