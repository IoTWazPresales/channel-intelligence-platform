from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimDistributor

router = APIRouter()


class DistributorCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=256)


class DistributorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)


@router.get("")
async def list_distributors(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DimDistributor).order_by(DimDistributor.code))
    rows = res.scalars().all()
    return [{"id": d.id, "code": d.code, "name": d.name} for d in rows]


@router.post("", status_code=201)
async def create_distributor(body: DistributorCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(DimDistributor).where(DimDistributor.code == body.code))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Distributor code already exists")
    row = DimDistributor(code=body.code.strip(), name=body.name.strip())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name}


@router.patch("/{distributor_id}")
async def patch_distributor(
    distributor_id: int, body: DistributorPatch, db: AsyncSession = Depends(get_db)
):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name}


@router.delete("/{distributor_id}", status_code=204)
async def delete_distributor(distributor_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimDistributor, distributor_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Distributor is still referenced by facts or other rows; remove those first.",
        ) from None
    return Response(status_code=204)
