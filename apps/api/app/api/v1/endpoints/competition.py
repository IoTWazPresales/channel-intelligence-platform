from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.api.deps import get_db
from app.models.dimensions import DimCompetitorBrand, DimCompetitorProduct, DimProduct
from app.models.facts import FactCompetitorMapping, FactCompetitorPrice
from app.services.competition.propose import propose_competitor_mappings

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


class ProposeBody(BaseModel):
    min_score: float = Field(default=0.55, ge=0, le=1)
    max_per_product: int = Field(default=3, ge=1, le=20)


class PriceImportRow(BaseModel):
    competitor_sku: str
    price: float = Field(gt=0)
    observed_at: datetime | None = None
    channel: str | None = None


class PriceImportBody(BaseModel):
    rows: list[PriceImportRow]


@router.get("/mappings")
async def list_mappings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactCompetitorMapping))
    rows = res.scalars().all()
    out = []
    for m in rows:
        prod = await db.get(DimProduct, m.product_id)
        comp = await db.get(DimCompetitorProduct, m.competitor_product_id)
        brand = await db.get(DimCompetitorBrand, comp.brand_id) if comp else None
        out.append(
            {
                "id": m.id,
                "product_id": m.product_id,
                "internal_sku": prod.sku if prod else None,
                "product_name": prod.name if prod else None,
                "competitor_sku": comp.sku if comp else None,
                "competitor_name": comp.name if comp else None,
                "competitor_brand": brand.name if brand else None,
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


@router.post("/mappings/propose")
async def propose_mappings(body: ProposeBody | None = None, db: AsyncSession = Depends(get_db)):
    """Score internal SKUs against competitor products and create pending mappings."""
    payload = body or ProposeBody()
    return await propose_competitor_mappings(
        db, min_score=payload.min_score, max_per_product=payload.max_per_product
    )


@router.post("/prices/import")
async def import_comp_prices(body: PriceImportBody, db: AsyncSession = Depends(get_db)):
    """Import competitor price observations against existing competitor SKUs.

    Does not create competitor products. Unknown SKUs are reported and skipped.
    """
    if not body.rows:
        raise HTTPException(status_code=400, detail="rows must not be empty")
    if len(body.rows) > 500:
        raise HTTPException(status_code=400, detail="at most 500 rows per import")
    created = 0
    skipped_unknown: list[str] = []
    for row in body.rows:
        sku = (row.competitor_sku or "").strip()
        if not sku:
            skipped_unknown.append("")
            continue
        res = await db.execute(select(DimCompetitorProduct).where(DimCompetitorProduct.sku == sku))
        comp = res.scalars().first()
        if not comp:
            skipped_unknown.append(sku)
            continue
        observed = row.observed_at or datetime.now(timezone.utc)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        db.add(
            FactCompetitorPrice(
                competitor_product_id=comp.id,
                observed_at=observed,
                price=row.price,
                channel=row.channel,
            )
        )
        created += 1
    if created:
        await db.commit()
    return {"created": created, "skipped_unknown_skus": skipped_unknown}
