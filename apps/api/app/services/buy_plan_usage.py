"""Rows that reference a buy plan (for delete UX and pre-delete unlink)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.derived import BuyRecommendation
from app.models.lineup import FactLineupPlanItem


async def buy_plan_reference_breakdown(db: AsyncSession, plan_id: int) -> list[dict[str, int | str]]:
    """Return `{label, count}` only where count > 0."""
    checks: list[tuple[str, object]] = [
        (
            "Buy recommendations (linked to this plan)",
            select(func.count())
            .select_from(BuyRecommendation)
            .where(BuyRecommendation.buy_plan_id == plan_id),
        ),
        (
            "Lineup plan items (cross-link)",
            select(func.count())
            .select_from(FactLineupPlanItem)
            .where(FactLineupPlanItem.link_buy_plan_id == plan_id),
        ),
    ]
    out: list[dict[str, int | str]] = []
    for label, stmt in checks:
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out
