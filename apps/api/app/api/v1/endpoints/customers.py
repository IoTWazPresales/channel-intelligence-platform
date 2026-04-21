from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_db
from app.models.dimensions import DimChannel, DimCustomer, DimRegion

router = APIRouter()


class CustomerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    region_id: int | None = None
    channel_id: int | None = None


class CustomerBulkRow(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    region_code: str | None = Field(default=None, max_length=32)
    channel_code: str | None = Field(default=None, max_length=32)


class CustomerBulkBody(BaseModel):
    rows: list[CustomerBulkRow]


@router.get("")
async def list_customers(db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(DimCustomer).options(joinedload(DimCustomer.region), joinedload(DimCustomer.channel))
    )
    items = res.unique().scalars().all()
    out = []
    for c in items:
        out.append(
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "region_id": c.region_id,
                "channel_id": c.channel_id,
                "region_code": c.region.code if c.region else None,
                "channel_code": c.channel.code if c.channel else None,
            }
        )
    out.sort(key=lambda x: x["code"])
    return out


@router.patch("/{customer_id}")
async def patch_customer(customer_id: int, body: CustomerPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimCustomer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
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
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name, "region_id": row.region_id, "channel_id": row.channel_id}


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
            db.add(DimCustomer(code=code, name=name, region_id=region_id, channel_id=channel_id))
            created += 1
    await db.commit()
    return {"created": created, "updated": updated, "total": len(body.rows)}


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimCustomer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Customer is still referenced by facts or other rows; remove those first.",
        ) from None
    return Response(status_code=204)
