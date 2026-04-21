from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimProduct
from app.models.facts import FactProductRoadmap

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("")
async def list_roadmap(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactProductRoadmap))
    rows = res.scalars().all()
    out = []
    for r in rows:
        prod = await db.get(DimProduct, r.product_id)
        out.append(
            {
                "id": r.id,
                "sku": prod.sku if prod else None,
                "lifecycle_phase": r.lifecycle_phase,
                "whitespace_flag": r.whitespace_flag,
                "overlap_flag": r.overlap_flag,
                "launch_target": r.launch_target.isoformat() if r.launch_target else None,
            }
        )
    return out


@router.delete("/{row_id}", status_code=204)
async def delete_roadmap_row(row_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactProductRoadmap, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/clear-all", status_code=200)
async def clear_roadmap(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactProductRoadmap))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
