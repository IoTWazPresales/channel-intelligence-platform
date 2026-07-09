from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.derived import PromoReadiness
from app.models.facts import FactPromotionPlan

router = APIRouter()

# Spec §7 / U6: park scaffold readers — prefer /commercial-planner/cpor-cases.
_PARKED = {
    "parked": True,
    "message": "Promo scaffold plans/readiness are parked. Use CPOR Cases.",
    "cpor_cases_href": "/commercial-planner/cpor-cases",
}


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/plans")
async def list_promo_plans(db: AsyncSession = Depends(get_db)):
    """Parked (spec §7): returns empty list + redirect hint. Code retained."""
    _ = db
    return []


@router.get("/readiness")
async def list_promo_readiness(db: AsyncSession = Depends(get_db)):
    """Parked (spec §7 / §11): readiness tab parked; code retained."""
    _ = db
    return []


@router.get("/meta")
async def promotions_meta():
    return _PARKED


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_promo_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactPromotionPlan, plan_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/plans/clear-all", status_code=200)
async def clear_promo_plans(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactPromotionPlan))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/readiness/{row_id}", status_code=204)
async def delete_promo_readiness(row_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(PromoReadiness, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/readiness/clear-all", status_code=200)
async def clear_promo_readiness(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(PromoReadiness))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
