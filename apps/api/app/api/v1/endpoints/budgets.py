from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimBudgetOwner
from app.models.derived import BudgetHealth
from app.models.facts import FactBudgetAllocation, FactBudgetRequest

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/allocations")
async def allocations(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactBudgetAllocation))
    rows = res.scalars().all()
    out = []
    for a in rows:
        owner = await db.get(DimBudgetOwner, a.owner_id)
        out.append(
            {
                "id": a.id,
                "owner": owner.name if owner else None,
                "category": a.category,
                "period_start": a.period_start.isoformat(),
                "envelope_type": a.envelope_type,
                "allocated_amount": float(a.allocated_amount),
            }
        )
    return out


@router.get("/requests")
async def requests(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactBudgetRequest))
    rows = res.scalars().all()
    out = []
    for r in rows:
        owner = await db.get(DimBudgetOwner, r.owner_id)
        out.append(
            {
                "id": r.id,
                "owner": owner.name if owner else None,
                "amount": float(r.amount),
                "initiative_type": r.initiative_type,
                "status": r.status,
                "justification_summary": r.justification_summary,
                "expected_impact": r.expected_impact,
                "risk_of_not_funding": r.risk_of_not_funding,
            }
        )
    return out


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BudgetHealth))
    rows = res.scalars().all()
    out = []
    for h in rows:
        owner = await db.get(DimBudgetOwner, h.owner_id)
        out.append(
            {
                "id": h.id,
                "owner": owner.name if owner else None,
                "remaining_amount": float(h.remaining_amount),
                "pressure_state": h.pressure_state,
                "period_start": h.period_start.isoformat(),
            }
        )
    return out


@router.delete("/allocations/{row_id}", status_code=204)
async def delete_allocation(row_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactBudgetAllocation, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/allocations/clear-all", status_code=200)
async def clear_allocations(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactBudgetAllocation))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/requests/{row_id}", status_code=204)
async def delete_budget_request(row_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactBudgetRequest, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/requests/clear-all", status_code=200)
async def clear_budget_requests(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactBudgetRequest))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/health/{row_id}", status_code=204)
async def delete_budget_health(row_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(BudgetHealth, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/health/clear-all", status_code=200)
async def clear_budget_health(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(BudgetHealth))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
