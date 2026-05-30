from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.feature_flags import commercial_planner_enabled
from app.models.derived import ExceptionInboxItem, StockHealth
from app.models.facts import FactBudgetRequest, FactInboundShipment
from app.services.commercial_planner.plan_readiness import commercial_planner_dashboard_aggregate

router = APIRouter()


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    stock_rows = await db.execute(select(StockHealth.health_state, func.count()).group_by(StockHealth.health_state))
    stock_summary = {row[0]: row[1] for row in stock_rows.all()}

    open_exceptions = await db.scalar(select(func.count()).select_from(ExceptionInboxItem).where(ExceptionInboxItem.status == "open")) or 0
    open_budget = await db.scalar(
        select(func.count()).select_from(FactBudgetRequest).where(FactBudgetRequest.status.in_(["draft", "submitted", "under_review"]))
    ) or 0
    late_risk = await db.scalar(
        select(func.count()).select_from(FactInboundShipment).where(FactInboundShipment.status != "received")
    ) or 0

    cp_kpis = None
    if commercial_planner_enabled():
        cp_kpis = await commercial_planner_dashboard_aggregate(db)

    recommended_actions = [
        {
            "title": "Review exceptions inbox",
            "href": "/exceptions",
            "reason": "Central queue for stock, pricing, and mapping issues.",
        },
        {
            "title": "Validate latest import",
            "href": "/admin/imports",
            "reason": "Trust layer for messy distributor files.",
        },
    ]
    if commercial_planner_enabled():
        recommended_actions.insert(
            0,
            {
                "title": "Commercial plans readiness",
                "href": "/commercial-planner",
                "reason": "Review plans missing terms, SKU assumptions, or economics flags.",
            },
        )

    return {
        "kpis": {
            "open_exceptions": open_exceptions,
            "open_budget_requests": open_budget,
            "inbound_shipments_tracked": late_risk,
            "commercial_planner": cp_kpis,
        },
        "stock_health": stock_summary,
        "recommended_actions": recommended_actions,
    }
