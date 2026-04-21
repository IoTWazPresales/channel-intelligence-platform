from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimChannel, DimRegion

router = APIRouter()


@router.get("/channels")
async def list_channels(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DimChannel).order_by(DimChannel.code))
    rows = res.scalars().all()
    return [{"id": c.id, "code": c.code, "name": c.name} for c in rows]


@router.get("/regions")
async def list_regions(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DimRegion).order_by(DimRegion.code))
    rows = res.scalars().all()
    return [{"id": r.id, "code": r.code, "name": r.name} for r in rows]
