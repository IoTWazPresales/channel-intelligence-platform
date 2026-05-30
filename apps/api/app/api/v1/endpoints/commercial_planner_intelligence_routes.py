"""Commercial planner intelligence routes (rankings snapshots)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.commercial_planner_auth import require_commercial_planner_enabled
from app.models.commercial_planner import CommercialPlan
from app.models.dimensions import DimCustomer, DimDistributor
from app.services.commercial_planner.intelligence.product_rankings import rank_products_for_customer
from app.services.commercial_planner.intelligence.ranking_snapshots import (
    get_ranking_snapshot,
    list_ranking_snapshots_for_plan,
    store_ranking_snapshot,
)

router = APIRouter(dependencies=[Depends(require_commercial_planner_enabled)])


@router.post("/plans/{plan_id}/intelligence/customer/{customer_id}/product-rankings/snapshot")
async def save_product_rankings_snapshot(
    plan_id: int,
    customer_id: int,
    distributor_id: int = Query(..., description="Distributor context for economics scoring"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Store latest deterministic rankings in-process for audit/replay (worker-local)."""
    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    if not await db.get(DimCustomer, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    if not await db.get(DimDistributor, distributor_id):
        raise HTTPException(status_code=404, detail="Distributor not found")
    items = await rank_products_for_customer(
        db,
        plan_id=plan_id,
        customer_id=customer_id,
        distributor_id=distributor_id,
        limit=limit,
    )
    snapshot = store_ranking_snapshot(
        plan_id=plan_id,
        customer_id=customer_id,
        distributor_id=distributor_id,
        items=items,
    )
    return snapshot


@router.get("/plans/{plan_id}/intelligence/snapshots")
async def list_plan_intelligence_snapshots(plan_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"plan_id": plan_id, "snapshots": list_ranking_snapshots_for_plan(plan_id)}


@router.get("/plans/{plan_id}/intelligence/customer/{customer_id}/product-rankings/snapshot")
async def get_product_rankings_snapshot(
    plan_id: int,
    customer_id: int,
    distributor_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    snap = get_ranking_snapshot(
        plan_id=plan_id,
        customer_id=customer_id,
        distributor_id=distributor_id,
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="No ranking snapshot stored for this customer/distributor")
    return snap
