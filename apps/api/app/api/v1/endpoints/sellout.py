from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactSalesSellout

router = APIRouter()


class SelloutPatch(BaseModel):
    distributor_id: int | None = None


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("")
async def list_sellout(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactSalesSellout).order_by(FactSalesSellout.period_start.desc()))
    rows = res.scalars().all()
    out = []
    for s in rows:
        prod = await db.get(DimProduct, s.product_id)
        cust = await db.get(DimCustomer, s.customer_id)
        dist = await db.get(DimDistributor, s.distributor_id) if s.distributor_id else None
        out.append(
            {
                "id": s.id,
                "product_sku": prod.sku if prod else None,
                "customer_code": cust.code if cust else None,
                "period_start": s.period_start.isoformat(),
                "units": float(s.units),
                "revenue": float(s.revenue),
                "distributor_id": s.distributor_id,
                "distributor_code": dist.code if dist else None,
                "unit_sellout_price_ex_tax_amount": float(s.unit_sellout_price_ex_tax_amount)
                if s.unit_sellout_price_ex_tax_amount is not None
                else None,
                "reported_revenue_amount": float(s.reported_revenue_amount)
                if s.reported_revenue_amount is not None
                else None,
                "computed_revenue_amount": float(s.computed_revenue_amount)
                if s.computed_revenue_amount is not None
                else None,
                "currency_code": s.currency_code,
                "source_import_job_id": s.source_import_job_id,
            }
        )
    return out


@router.patch("/{sellout_id}")
async def patch_sellout(sellout_id: int, body: SelloutPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactSalesSellout, sellout_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "distributor_id" in data:
        did = data["distributor_id"]
        if did is not None:
            d = await db.get(DimDistributor, did)
            if not d:
                raise HTTPException(status_code=400, detail="Invalid distributor_id")
        row.distributor_id = did
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "distributor_id": row.distributor_id}


@router.delete("/{sellout_id}", status_code=204)
async def delete_sellout(sellout_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactSalesSellout, sellout_id)
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
async def clear_sellout(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactSalesSellout))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
