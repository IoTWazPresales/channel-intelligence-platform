from datetime import datetime, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_db
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
from app.services.customer_usage import (
    cleanup_soft_customer_references,
    customer_hard_reference_breakdown,
    delete_customer_children,
)
from app.services.customer_location_usage import customer_location_hard_reference_breakdown
from app.services.master_entity_bulk_delete import confirm_master_bulk_delete, preview_master_bulk_delete

router = APIRouter()


class MasterBulkIdsBody(BaseModel):
    entity_ids: list[int] = Field(default_factory=list, max_length=200)

ALLOWED_CUSTOMER_STATUS = {"active", "inactive", "onboarding", "blocked", "unverified", "needs_review"}
ALLOWED_PARTNER_TIER = {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail", "unmanaged"}
TMP_CUSTOMER_CODE_PREFIX = "TMP-CUST"
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
async def post_customers_bulk_delete_preview(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid customer id."},
        )
    return await preview_master_bulk_delete(db, "customers", body.entity_ids)


@router.post("/bulk-delete-confirm")
async def post_customers_bulk_delete_confirm(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid customer id."},
        )
    try:
        return await confirm_master_bulk_delete(db, "customers", body.entity_ids)
    except ValueError as exc:
        code = str(exc)
        if code == "not_all_entities_found":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": code,
                    "message": "One or more customer ids no longer exist; refresh the list and try again.",
                },
            ) from None
        if code == "entities_still_blocked":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": code,
                    "message": "No selected customers can be deleted; all are still referenced.",
                },
            ) from None
        raise


@router.patch("/{customer_id}")
async def patch_customer(customer_id: int, body: CustomerPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimCustomer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
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
    }


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
