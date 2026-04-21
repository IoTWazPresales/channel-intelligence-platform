from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.derived import BuyRecommendation
from app.models.dimensions import DimProduct
from app.models.facts import FactBuyPlan
from app.models.lineup import FactLineupPlanItem
from app.services.buy_plan_usage import buy_plan_reference_breakdown

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("")
async def list_buy_plans(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactBuyPlan))
    rows = res.scalars().all()
    out = []
    for b in rows:
        prod = await db.get(DimProduct, b.product_id)
        out.append(
            {
                "id": b.id,
                "sku": prod.sku if prod else None,
                "recommended_qty": float(b.recommended_qty),
                "window_start": b.recommended_window_start.isoformat(),
                "window_end": b.recommended_window_end.isoformat(),
                "rationale": b.rationale,
                "risk_if_not_ordered": b.risk_if_not_ordered,
            }
        )
    return out


@router.get("/references")
async def get_buy_plan_references_query(plan_id: int = Query(..., ge=1), db: AsyncSession = Depends(get_db)):
    """Same payload as path variant; query form avoids any `{plan_id}` / multi-segment routing edge cases."""
    row = await db.get(FactBuyPlan, plan_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "buy_plan_not_found", "plan_id": plan_id})
    refs = await buy_plan_reference_breakdown(db, plan_id)
    prod = await db.get(DimProduct, row.product_id)
    return {"sku": prod.sku if prod else None, "references": refs, "blocked": len(refs) > 0}


@router.get("/{plan_id}/references")
async def get_buy_plan_references(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Counts of rows that still point at this buy plan (nullable cross-links)."""
    row = await db.get(FactBuyPlan, plan_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "buy_plan_not_found", "plan_id": plan_id})
    refs = await buy_plan_reference_breakdown(db, plan_id)
    prod = await db.get(DimProduct, row.product_id)
    return {"sku": prod.sku if prod else None, "references": refs, "blocked": len(refs) > 0}


@router.post("/clear-all", status_code=200)
async def clear_buy_plans(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    plan_ids = (await db.execute(select(FactBuyPlan.id))).scalars().all()
    if plan_ids:
        await db.execute(
            update(BuyRecommendation)
            .where(BuyRecommendation.buy_plan_id.in_(plan_ids))
            .values(buy_plan_id=None)
        )
        await db.execute(
            update(FactLineupPlanItem)
            .where(FactLineupPlanItem.link_buy_plan_id.in_(plan_ids))
            .values(link_buy_plan_id=None)
        )
    try:
        res = await db.execute(delete(FactBuyPlan))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/id/{plan_id}", status_code=204)
async def delete_buy_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactBuyPlan, plan_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    # Nullable planning cross-links would otherwise 409 with no UI to clear them.
    await db.execute(
        update(BuyRecommendation).where(BuyRecommendation.buy_plan_id == plan_id).values(buy_plan_id=None)
    )
    await db.execute(
        update(FactLineupPlanItem)
        .where(FactLineupPlanItem.link_buy_plan_id == plan_id)
        .values(link_buy_plan_id=None)
    )
    await db.flush()
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs = await buy_plan_reference_breakdown(db, plan_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Buy plan could not be deleted (database constraint). Dependent data may have changed.",
                "references": refs
                if refs
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)
