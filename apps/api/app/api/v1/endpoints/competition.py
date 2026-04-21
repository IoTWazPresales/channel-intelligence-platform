from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimCompetitorProduct, DimProduct
from app.models.facts import FactCompetitorMapping, FactCompetitorPrice

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/mappings")
async def list_mappings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactCompetitorMapping))
    rows = res.scalars().all()
    out = []
    for m in rows:
        prod = await db.get(DimProduct, m.product_id)
        comp = await db.get(DimCompetitorProduct, m.competitor_product_id)
        out.append(
            {
                "id": m.id,
                "internal_sku": prod.sku if prod else None,
                "competitor_sku": comp.sku if comp else None,
                "score": float(m.score),
                "explanation": m.explanation,
                "approval_status": m.approval_status,
            }
        )
    return out


@router.get("/prices")
async def list_comp_prices(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactCompetitorPrice).order_by(FactCompetitorPrice.observed_at.desc()))
    rows = res.scalars().all()
    out = []
    for p in rows:
        comp = await db.get(DimCompetitorProduct, p.competitor_product_id)
        out.append(
            {
                "id": p.id,
                "competitor_sku": comp.sku if comp else None,
                "observed_at": p.observed_at.isoformat(),
                "price": float(p.price),
                "channel": p.channel,
            }
        )
    return out


@router.post("/mappings/{mapping_id}/approve")
async def approve_mapping(mapping_id: int, db: AsyncSession = Depends(get_db)):
    m = await db.get(FactCompetitorMapping, mapping_id)
    if not m:
        return {"ok": False}
    m.approval_status = "approved"
    await db.commit()
    return {"ok": True, "id": mapping_id, "approval_status": m.approval_status}


@router.post("/mappings/{mapping_id}/reject")
async def reject_mapping(mapping_id: int, db: AsyncSession = Depends(get_db)):
    m = await db.get(FactCompetitorMapping, mapping_id)
    if not m:
        return {"ok": False}
    m.approval_status = "rejected"
    await db.commit()
    return {"ok": True, "id": mapping_id, "approval_status": m.approval_status}


@router.delete("/mappings/{mapping_id}", status_code=204)
async def delete_mapping(mapping_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactCompetitorMapping, mapping_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/mappings/clear-all", status_code=200)
async def clear_mappings(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactCompetitorMapping))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/prices/{price_id}", status_code=204)
async def delete_comp_price(price_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactCompetitorPrice, price_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/prices/clear-all", status_code=200)
async def clear_comp_prices(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactCompetitorPrice))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
