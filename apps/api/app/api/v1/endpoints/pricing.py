from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimProduct
from app.models.derived import PricingRecommendation
from app.models.facts import FactPricing
from app.services.facts_upsert import get_or_create_product, resolve_channel_id, resolve_customer_id

router = APIRouter()


class PricingFactRowIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    net_price: float
    list_price: float
    effective_date: str = Field(min_length=8, max_length=32)
    currency: str = Field(default="USD", max_length=8)
    customer_code: str | None = Field(default=None, max_length=64)
    channel_code: str | None = Field(default=None, max_length=32)


class PricingFactsBulkBody(BaseModel):
    rows: list[PricingFactRowIn]


class ClearConfirmBody(BaseModel):
    confirm: bool = False


def _parse_iso_date(s: str) -> date:
    s = s.strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        y, m, d = (int(x) for x in s.split("-", 2))
        return date(y, m, d)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid date {s!r}") from exc


@router.get("/facts")
async def list_pricing_facts(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactPricing).order_by(FactPricing.effective_date.desc()))
    rows = res.scalars().all()
    out = []
    for p in rows:
        prod = await db.get(DimProduct, p.product_id)
        out.append(
            {
                "id": p.id,
                "sku": prod.sku if prod else None,
                "effective_date": p.effective_date.isoformat(),
                "list_price": float(p.list_price),
                "net_price": float(p.net_price),
                "currency": p.currency,
            }
        )
    return out


@router.post("/facts", status_code=201)
async def create_pricing_fact(row: PricingFactRowIn, db: AsyncSession = Depends(get_db)):
    try:
        eff = _parse_iso_date(row.effective_date)
        prod = await get_or_create_product(db, row.sku)
        cust_id = await resolve_customer_id(db, row.customer_code, create=True)
        ch_id = (
            await resolve_channel_id(db, row.channel_code.strip())
            if row.channel_code and row.channel_code.strip()
            else None
        )
        fact = FactPricing(
            product_id=prod.id,
            customer_id=cust_id,
            channel_id=ch_id,
            effective_date=eff,
            list_price=row.list_price,
            net_price=row.net_price,
            currency=row.currency.strip() or "USD",
        )
        db.add(fact)
        await db.commit()
        await db.refresh(fact)
        return {"id": fact.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/facts/bulk", status_code=200)
async def bulk_create_pricing_facts(body: PricingFactsBulkBody, db: AsyncSession = Depends(get_db)):
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    n = 0
    for row in body.rows:
        try:
            eff = _parse_iso_date(row.effective_date)
            prod = await get_or_create_product(db, row.sku)
            cust_id = await resolve_customer_id(db, row.customer_code, create=True)
            ch_id = None
            if row.channel_code and row.channel_code.strip():
                ch_id = await resolve_channel_id(db, row.channel_code.strip())
            fact = FactPricing(
                product_id=prod.id,
                customer_id=cust_id,
                channel_id=ch_id,
                effective_date=eff,
                list_price=row.list_price,
                net_price=row.net_price,
                currency=(row.currency or "USD").strip() or "USD",
            )
            db.add(fact)
            n += 1
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return {"created": n}


@router.get("/recommendations")
async def list_pricing_recommendations(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PricingRecommendation))
    rows = res.scalars().all()
    out = []
    for r in rows:
        prod = await db.get(DimProduct, r.product_id)
        out.append(
            {
                "id": r.id,
                "sku": prod.sku if prod else None,
                "suggested_state": r.suggested_state,
                "explanation_summary": r.explanation_summary,
                "explanation_factors": r.explanation_factors,
                "confidence": r.confidence,
                "action_owner": r.action_owner,
            }
        )
    return out


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_pricing_fact(fact_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactPricing, fact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/facts/clear-all", status_code=200)
async def clear_pricing_facts(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactPricing))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/recommendations/{rec_id}", status_code=204)
async def delete_pricing_recommendation(rec_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(PricingRecommendation, rec_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/recommendations/clear-all", status_code=200)
async def clear_pricing_recommendations(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(PricingRecommendation))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
