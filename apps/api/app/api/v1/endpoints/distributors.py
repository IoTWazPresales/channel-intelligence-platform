from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimDistributor, DistributorContact, DistributorLocation
from app.models.facts import FactInboundShipment, FactSalesSellout
from app.models.import_distributor_si import DistributorSourceTokenAlias
from app.models.ingestion import ImportJob
from app.services.distributor_usage import (
    delete_distributor_children,
    distributor_hard_reference_breakdown,
)

router = APIRouter()

ALLOWED_DISTRIBUTOR_LOCATION_TYPES = {"hq", "branch", "warehouse", "office", "store", "other"}
ALLOWED_DISTRIBUTOR_CONTACT_ROLES = {"general", "executive", "sales", "operations", "finance", "support", "other"}


class DistributorCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    distributor_code: str = Field(min_length=1, max_length=32, alias="code")
    distributor_name: str = Field(min_length=1, max_length=256, alias="name")


class DistributorPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    distributor_name: str | None = Field(default=None, min_length=1, max_length=256, alias="name")


class DistributorLocationCreate(BaseModel):
    location_code: str = Field(min_length=1, max_length=64)
    location_name: str = Field(min_length=1, max_length=256)
    location_type: str = Field(default="branch", min_length=1, max_length=32)
    country_code: str | None = Field(default=None, min_length=2, max_length=8)
    address_summary: str | None = Field(default=None, max_length=512)
    is_active: bool = True
    notes_summary: str | None = Field(default=None, max_length=512)


class DistributorLocationPatch(BaseModel):
    location_code: str | None = Field(default=None, min_length=1, max_length=64)
    location_name: str | None = Field(default=None, min_length=1, max_length=256)
    location_type: str | None = Field(default=None, min_length=1, max_length=32)
    country_code: str | None = Field(default=None, min_length=2, max_length=8)
    address_summary: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None
    notes_summary: str | None = Field(default=None, max_length=512)


class DistributorContactCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=256)
    contact_role: str = Field(default="general", min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    is_primary: bool = False
    is_active: bool = True
    notes_summary: str | None = Field(default=None, max_length=512)


class DistributorContactPatch(BaseModel):
    contact_name: str | None = Field(default=None, min_length=1, max_length=256)
    contact_role: str | None = Field(default=None, min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    is_primary: bool | None = None
    is_active: bool | None = None
    notes_summary: str | None = Field(default=None, max_length=512)


def _linkage_status(
    linked_sellout_rows: int,
    total_sellout_rows: int,
    linked_inbound_rows: int,
    total_inbound_rows: int,
) -> str:
    total_rows = total_sellout_rows + total_inbound_rows
    linked_rows = linked_sellout_rows + linked_inbound_rows
    if total_rows == 0:
        return "no_fact_links"
    if linked_rows == 0:
        return "unmapped"
    if linked_rows < total_rows:
        return "partial"
    return "healthy"


@router.get("")
async def list_distributors(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    q: str = Query(default=""),
    linkage_status: str = Query(default=""),
    min_alias_count: int | None = Query(default=None, ge=0),
    alias_link: str | None = Query(default=None, description="Filter: linked (≥1 alias) or unlinked (0 aliases)"),
    sort_by: str = Query(default="distributor_code"),
    sort_dir: str = Query(default="asc"),
):
    sellout_agg = (
        select(
            FactSalesSellout.distributor_id.label("distributor_id"),
            func.count(FactSalesSellout.id).label("linked_sellout_rows"),
            func.max(FactSalesSellout.period_start).label("latest_sellout_period_start"),
        )
        .where(FactSalesSellout.distributor_id.is_not(None))
        .group_by(FactSalesSellout.distributor_id)
        .subquery()
    )
    inbound_agg = (
        select(
            FactInboundShipment.distributor_id.label("distributor_id"),
            func.count(FactInboundShipment.id).label("linked_inbound_rows"),
            func.max(FactInboundShipment.eta_date).label("latest_inbound_eta_date"),
        )
        .where(FactInboundShipment.distributor_id.is_not(None))
        .group_by(FactInboundShipment.distributor_id)
        .subquery()
    )
    sellout_unmapped = (
        select(func.count(FactSalesSellout.id))
        .where(FactSalesSellout.distributor_id.is_(None))
        .scalar_subquery()
    )
    inbound_unmapped = (
        select(func.count(FactInboundShipment.id))
        .where(FactInboundShipment.distributor_id.is_(None))
        .scalar_subquery()
    )

    linked_sellout_col = func.coalesce(sellout_agg.c.linked_sellout_rows, 0)
    linked_inbound_col = func.coalesce(inbound_agg.c.linked_inbound_rows, 0)
    total_sellout_col = linked_sellout_col + sellout_unmapped
    total_inbound_col = linked_inbound_col + inbound_unmapped
    location_count_subq = (
        select(
            DistributorLocation.distributor_id.label("distributor_id"),
            func.count(DistributorLocation.id).label("location_count"),
        )
        .group_by(DistributorLocation.distributor_id)
        .subquery()
    )
    contact_count_subq = (
        select(
            DistributorContact.distributor_id.label("distributor_id"),
            func.count(DistributorContact.id).label("contact_count"),
        )
        .group_by(DistributorContact.distributor_id)
        .subquery()
    )
    dist_alias_count_sq = (
        select(func.count())
        .select_from(DistributorSourceTokenAlias)
        .where(
            DistributorSourceTokenAlias.distributor_id == DimDistributor.id,
            DistributorSourceTokenAlias.status == "approved",
        )
        .correlate(DimDistributor)
        .scalar_subquery()
    )
    dist_last_import_sq = (
        select(func.max(ImportJob.created_at))
        .select_from(DistributorSourceTokenAlias)
        .join(ImportJob, ImportJob.id == DistributorSourceTokenAlias.created_from_import_job_id)
        .where(DistributorSourceTokenAlias.distributor_id == DimDistributor.id)
        .correlate(DimDistributor)
        .scalar_subquery()
    )

    base = (
        select(
            DimDistributor.id.label("id"),
            DimDistributor.code.label("distributor_code"),
            DimDistributor.name.label("distributor_name"),
            DimDistributor.created_at.label("dim_created_at"),
            DimDistributor.updated_at.label("dim_updated_at"),
            linked_sellout_col.label("linked_sellout_rows"),
            linked_inbound_col.label("linked_inbound_rows"),
            total_sellout_col.label("total_sellout_rows"),
            total_inbound_col.label("total_inbound_rows"),
            func.coalesce(location_count_subq.c.location_count, 0).label("location_count"),
            func.coalesce(contact_count_subq.c.contact_count, 0).label("contact_count"),
            dist_alias_count_sq.label("alias_count"),
            dist_last_import_sq.label("last_import_at"),
            sellout_agg.c.latest_sellout_period_start.label("latest_sellout_period_start"),
            inbound_agg.c.latest_inbound_eta_date.label("latest_inbound_eta_date"),
        )
        .select_from(DimDistributor)
        .outerjoin(sellout_agg, sellout_agg.c.distributor_id == DimDistributor.id)
        .outerjoin(inbound_agg, inbound_agg.c.distributor_id == DimDistributor.id)
        .outerjoin(location_count_subq, location_count_subq.c.distributor_id == DimDistributor.id)
        .outerjoin(contact_count_subq, contact_count_subq.c.distributor_id == DimDistributor.id)
    )

    q_val = q.strip()
    if q_val:
        like_q = f"%{q_val}%"
        base = base.where(or_(DimDistributor.code.ilike(like_q), DimDistributor.name.ilike(like_q)))

    linkage_filters = {
        "healthy": and_(linked_sellout_col == total_sellout_col, linked_inbound_col == total_inbound_col),
        "partial": or_(
            and_(linked_sellout_col > 0, linked_sellout_col < total_sellout_col),
            and_(linked_inbound_col > 0, linked_inbound_col < total_inbound_col),
        ),
        "unmapped": and_(linked_sellout_col + linked_inbound_col == 0, total_sellout_col + total_inbound_col > 0),
        "no_fact_links": and_(total_sellout_col == 0, total_inbound_col == 0),
    }
    if linkage_status in linkage_filters:
        base = base.where(linkage_filters[linkage_status])

    if min_alias_count is not None:
        base = base.where(dist_alias_count_sq >= int(min_alias_count))

    al = (alias_link or "").strip().lower()
    if al == "linked":
        base = base.where(dist_alias_count_sq > 0)
    elif al == "unlinked":
        base = base.where(dist_alias_count_sq == 0)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    sort_exprs = {
        "id": DimDistributor.id,
        "distributor_code": DimDistributor.code,
        "distributor_name": DimDistributor.name,
        "created_at": DimDistributor.created_at,
        "updated_at": DimDistributor.updated_at,
        "location_count": func.coalesce(location_count_subq.c.location_count, 0),
        "contact_count": func.coalesce(contact_count_subq.c.contact_count, 0),
        "latest_sellout_period_start": sellout_agg.c.latest_sellout_period_start,
        "latest_inbound_eta_date": inbound_agg.c.latest_inbound_eta_date,
        "linked_sellout_rows": linked_sellout_col,
        "linked_inbound_rows": linked_inbound_col,
        "alias_count": dist_alias_count_sq,
        "last_import_at": dist_last_import_sq,
    }
    order_col = sort_exprs.get(sort_by, DimDistributor.code)
    if sort_dir == "desc":
        base = base.order_by(desc(order_col), DimDistributor.code.asc())
    else:
        base = base.order_by(order_col.asc(), DimDistributor.code.asc())

    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).all()
    items = []
    for r in rows:
        latest_sellout = r.latest_sellout_period_start.isoformat() if r.latest_sellout_period_start else None
        latest_inbound = r.latest_inbound_eta_date.isoformat() if r.latest_inbound_eta_date else None
        n_aliases = int(r.alias_count or 0)
        last_imp = r.last_import_at.isoformat() if r.last_import_at is not None else None
        m = getattr(r, "_mapping", None)
        if m is not None:
            dim_created = m.get("dim_created_at")
            dim_updated = m.get("dim_updated_at")
        else:
            dim_created = getattr(r, "dim_created_at", None)
            dim_updated = getattr(r, "dim_updated_at", None)
        items.append(
            {
                "id": r.id,
                "distributor_code": r.distributor_code,
                "distributor_name": r.distributor_name,
                "created_at": dim_created.isoformat() if dim_created is not None else None,
                "updated_at": dim_updated.isoformat() if dim_updated is not None else None,
                "linked_sellout_rows": int(r.linked_sellout_rows or 0),
                "linked_inbound_rows": int(r.linked_inbound_rows or 0),
                "total_sellout_rows": int(r.total_sellout_rows or 0),
                "total_inbound_rows": int(r.total_inbound_rows or 0),
                "location_count": int(r.location_count or 0),
                "contact_count": int(r.contact_count or 0),
                "alias_count": n_aliases,
                "last_import_at": last_imp,
                "alias_link_status": "linked" if n_aliases > 0 else "unlinked",
                "latest_sellout_period_start": latest_sellout,
                "latest_inbound_eta_date": latest_inbound,
                "linkage_status": _linkage_status(
                    int(r.linked_sellout_rows or 0),
                    int(r.total_sellout_rows or 0),
                    int(r.linked_inbound_rows or 0),
                    int(r.total_inbound_rows or 0),
                ),
                # Backward compatibility for older callers.
                "code": r.distributor_code,
                "name": r.distributor_name,
            }
        )

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "sort_by": sort_by if sort_by in sort_exprs else "distributor_code",
        "sort_dir": "desc" if sort_dir == "desc" else "asc",
    }


@router.get("/{distributor_id}")
async def get_distributor_detail(distributor_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    linked_sellout = (
        await db.execute(
            select(func.count(FactSalesSellout.id)).where(FactSalesSellout.distributor_id == distributor_id)
        )
    ).scalar_one()
    linked_inbound = (
        await db.execute(
            select(func.count(FactInboundShipment.id)).where(FactInboundShipment.distributor_id == distributor_id)
        )
    ).scalar_one()
    latest_sellout: date | None = (
        await db.execute(
            select(func.max(FactSalesSellout.period_start)).where(FactSalesSellout.distributor_id == distributor_id)
        )
    ).scalar_one()
    latest_inbound: date | None = (
        await db.execute(
            select(func.max(FactInboundShipment.eta_date)).where(FactInboundShipment.distributor_id == distributor_id)
        )
    ).scalar_one()
    total_sellout = linked_sellout + (
        await db.execute(select(func.count(FactSalesSellout.id)).where(FactSalesSellout.distributor_id.is_(None)))
    ).scalar_one()
    total_inbound = linked_inbound + (
        await db.execute(select(func.count(FactInboundShipment.id)).where(FactInboundShipment.distributor_id.is_(None)))
    ).scalar_one()
    location_count = (
        await db.execute(
            select(func.count(DistributorLocation.id)).where(DistributorLocation.distributor_id == distributor_id)
        )
    ).scalar_one()
    contact_count = (
        await db.execute(
            select(func.count(DistributorContact.id)).where(DistributorContact.distributor_id == distributor_id)
        )
    ).scalar_one()
    return {
        "id": row.id,
        "distributor_code": row.code,
        "distributor_name": row.name,
        "linked_sellout_rows": int(linked_sellout),
        "linked_inbound_rows": int(linked_inbound),
        "total_sellout_rows": int(total_sellout),
        "total_inbound_rows": int(total_inbound),
        "location_count": int(location_count),
        "contact_count": int(contact_count),
        "latest_sellout_period_start": latest_sellout.isoformat() if latest_sellout else None,
        "latest_inbound_eta_date": latest_inbound.isoformat() if latest_inbound else None,
        "linkage_status": _linkage_status(
            int(linked_sellout),
            int(total_sellout),
            int(linked_inbound),
            int(total_inbound),
        ),
    }


@router.post("", status_code=201)
async def create_distributor(body: DistributorCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(DimDistributor).where(DimDistributor.code == body.distributor_code.strip()))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Distributor code already exists")
    row = DimDistributor(code=body.distributor_code.strip(), name=body.distributor_name.strip())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "distributor_code": row.code,
        "distributor_name": row.name,
        "code": row.code,
        "name": row.name,
    }


@router.patch("/{distributor_id}")
async def patch_distributor(
    distributor_id: int, body: DistributorPatch, db: AsyncSession = Depends(get_db)
):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "distributor_name" in data and data["distributor_name"] is not None:
        row.name = data["distributor_name"].strip()
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "distributor_code": row.code,
        "distributor_name": row.name,
        "code": row.code,
        "name": row.name,
    }


async def _distributor_references_bundle(db: AsyncSession, distributor_id: int) -> dict:
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(
            status_code=404, detail={"error": "distributor_not_found", "distributor_id": distributor_id}
        )
    refs = await distributor_hard_reference_breakdown(db, distributor_id)
    return {"distributor_code": row.code, "references": refs, "blocked": len(refs) > 0}


@router.get("/references")
async def get_distributor_references_by_query(
    distributor_id: int = Query(..., ge=1, description="dim_distributor.id"),
    db: AsyncSession = Depends(get_db),
):
    return await _distributor_references_bundle(db, distributor_id)


@router.get("/id/{distributor_id}/refs")
async def get_distributor_refs_for_delete_ux(distributor_id: int, db: AsyncSession = Depends(get_db)):
    return await _distributor_references_bundle(db, distributor_id)


@router.get("/{distributor_id}/references")
async def get_distributor_references(distributor_id: int, db: AsyncSession = Depends(get_db)):
    return await _distributor_references_bundle(db, distributor_id)


@router.delete("/{distributor_id}", status_code=204)
async def delete_distributor(distributor_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    refs = await distributor_hard_reference_breakdown(db, distributor_id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Distributor is still referenced; remove or clear dependent rows first.",
                "references": refs,
            },
        )
    await delete_distributor_children(db, distributor_id)
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs2 = await distributor_hard_reference_breakdown(db, distributor_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Distributor could not be deleted (database constraint). Dependent data may have changed.",
                "references": refs2
                if refs2
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)


@router.get("/{distributor_id}/locations")
async def list_distributor_locations(distributor_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Distributor not found")
    res = await db.execute(
        select(DistributorLocation)
        .where(DistributorLocation.distributor_id == distributor_id)
        .order_by(DistributorLocation.location_code)
    )
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "distributor_id": r.distributor_id,
            "location_code": r.location_code,
            "location_name": r.location_name,
            "location_type": r.location_type,
            "country_code": r.country_code,
            "address_summary": r.address_summary,
            "is_active": r.is_active,
            "notes_summary": r.notes_summary,
        }
        for r in rows
    ]


@router.post("/{distributor_id}/locations", status_code=201)
async def create_distributor_location(
    distributor_id: int, body: DistributorLocationCreate, db: AsyncSession = Depends(get_db)
):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Distributor not found")
    location_type = body.location_type.strip().lower()
    if location_type not in ALLOWED_DISTRIBUTOR_LOCATION_TYPES:
        raise HTTPException(status_code=400, detail="location_type is invalid")
    country = body.country_code.strip().upper() if body.country_code else None
    rec = DistributorLocation(
        distributor_id=distributor_id,
        location_code=body.location_code.strip(),
        location_name=body.location_name.strip(),
        location_type=location_type,
        country_code=country,
        address_summary=body.address_summary.strip() if body.address_summary else None,
        is_active=body.is_active,
        notes_summary=body.notes_summary.strip() if body.notes_summary else None,
    )
    db.add(rec)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Location code already exists for this distributor") from None
    await db.refresh(rec)
    return {
        "id": rec.id,
        "distributor_id": rec.distributor_id,
        "location_code": rec.location_code,
        "location_name": rec.location_name,
        "location_type": rec.location_type,
        "country_code": rec.country_code,
        "address_summary": rec.address_summary,
        "is_active": rec.is_active,
        "notes_summary": rec.notes_summary,
    }


@router.patch("/{distributor_id}/locations/{location_id}")
async def patch_distributor_location(
    distributor_id: int,
    location_id: int,
    body: DistributorLocationPatch,
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(DistributorLocation, location_id)
    if not rec or rec.distributor_id != distributor_id:
        raise HTTPException(status_code=404, detail="Location not found")
    data = body.model_dump(exclude_unset=True)
    if "location_code" in data and data["location_code"] is not None:
        rec.location_code = data["location_code"].strip()
    if "location_name" in data and data["location_name"] is not None:
        rec.location_name = data["location_name"].strip()
    if "location_type" in data and data["location_type"] is not None:
        location_type = data["location_type"].strip().lower()
        if location_type not in ALLOWED_DISTRIBUTOR_LOCATION_TYPES:
            raise HTTPException(status_code=400, detail="location_type is invalid")
        rec.location_type = location_type
    if "country_code" in data:
        rec.country_code = data["country_code"].strip().upper() if data["country_code"] else None
    if "address_summary" in data:
        rec.address_summary = data["address_summary"].strip() if data["address_summary"] else None
    if "notes_summary" in data:
        rec.notes_summary = data["notes_summary"].strip() if data["notes_summary"] else None
    if "is_active" in data and data["is_active"] is not None:
        rec.is_active = data["is_active"]
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Location code already exists for this distributor") from None
    await db.refresh(rec)
    return {
        "id": rec.id,
        "distributor_id": rec.distributor_id,
        "location_code": rec.location_code,
        "location_name": rec.location_name,
        "location_type": rec.location_type,
        "country_code": rec.country_code,
        "address_summary": rec.address_summary,
        "is_active": rec.is_active,
        "notes_summary": rec.notes_summary,
    }


@router.delete("/{distributor_id}/locations/{location_id}", status_code=204)
async def delete_distributor_location(
    distributor_id: int, location_id: int, db: AsyncSession = Depends(get_db)
):
    rec = await db.get(DistributorLocation, location_id)
    if not rec or rec.distributor_id != distributor_id:
        raise HTTPException(status_code=404, detail="Location not found")
    await db.delete(rec)
    await db.commit()
    return Response(status_code=204)


@router.get("/{distributor_id}/contacts")
async def list_distributor_contacts(distributor_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Distributor not found")
    res = await db.execute(
        select(DistributorContact)
        .where(DistributorContact.distributor_id == distributor_id)
        .order_by(desc(DistributorContact.is_primary), DistributorContact.contact_name)
    )
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "distributor_id": r.distributor_id,
            "contact_name": r.contact_name,
            "contact_role": r.contact_role,
            "email": r.email,
            "phone": r.phone,
            "is_primary": r.is_primary,
            "is_active": r.is_active,
            "notes_summary": r.notes_summary,
        }
        for r in rows
    ]


@router.post("/{distributor_id}/contacts", status_code=201)
async def create_distributor_contact(
    distributor_id: int, body: DistributorContactCreate, db: AsyncSession = Depends(get_db)
):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Distributor not found")
    role = body.contact_role.strip().lower()
    if role not in ALLOWED_DISTRIBUTOR_CONTACT_ROLES:
        raise HTTPException(status_code=400, detail="contact_role is invalid")
    rec = DistributorContact(
        distributor_id=distributor_id,
        contact_name=body.contact_name.strip(),
        contact_role=role,
        email=body.email.strip() if body.email else None,
        phone=body.phone.strip() if body.phone else None,
        is_primary=body.is_primary,
        is_active=body.is_active,
        notes_summary=body.notes_summary.strip() if body.notes_summary else None,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return {
        "id": rec.id,
        "distributor_id": rec.distributor_id,
        "contact_name": rec.contact_name,
        "contact_role": rec.contact_role,
        "email": rec.email,
        "phone": rec.phone,
        "is_primary": rec.is_primary,
        "is_active": rec.is_active,
        "notes_summary": rec.notes_summary,
    }


@router.patch("/{distributor_id}/contacts/{contact_id}")
async def patch_distributor_contact(
    distributor_id: int,
    contact_id: int,
    body: DistributorContactPatch,
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(DistributorContact, contact_id)
    if not rec or rec.distributor_id != distributor_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    data = body.model_dump(exclude_unset=True)
    if "contact_name" in data and data["contact_name"] is not None:
        rec.contact_name = data["contact_name"].strip()
    if "contact_role" in data and data["contact_role"] is not None:
        role = data["contact_role"].strip().lower()
        if role not in ALLOWED_DISTRIBUTOR_CONTACT_ROLES:
            raise HTTPException(status_code=400, detail="contact_role is invalid")
        rec.contact_role = role
    if "email" in data:
        rec.email = data["email"].strip() if data["email"] else None
    if "phone" in data:
        rec.phone = data["phone"].strip() if data["phone"] else None
    if "notes_summary" in data:
        rec.notes_summary = data["notes_summary"].strip() if data["notes_summary"] else None
    if "is_primary" in data and data["is_primary"] is not None:
        rec.is_primary = data["is_primary"]
    if "is_active" in data and data["is_active"] is not None:
        rec.is_active = data["is_active"]
    await db.commit()
    await db.refresh(rec)
    return {
        "id": rec.id,
        "distributor_id": rec.distributor_id,
        "contact_name": rec.contact_name,
        "contact_role": rec.contact_role,
        "email": rec.email,
        "phone": rec.phone,
        "is_primary": rec.is_primary,
        "is_active": rec.is_active,
        "notes_summary": rec.notes_summary,
    }


@router.delete("/{distributor_id}/contacts/{contact_id}", status_code=204)
async def delete_distributor_contact(
    distributor_id: int, contact_id: int, db: AsyncSession = Depends(get_db)
):
    rec = await db.get(DistributorContact, contact_id)
    if not rec or rec.distributor_id != distributor_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(rec)
    await db.commit()
    return Response(status_code=204)
