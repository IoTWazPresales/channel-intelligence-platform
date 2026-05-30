"""Channel delete: hard blockers (nullable FKs on masters and facts)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimProduct
from app.models.facts import FactActivation, FactPricing, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader
from app.models.lineup import FactLineupPlanItem


def _hard_reference_checks(channel_id: int) -> list[tuple[str, object]]:
    return [
        (
            "Products (primary channel)",
            select(func.count()).select_from(DimProduct).where(DimProduct.channel_id == channel_id),
        ),
        (
            "Customers",
            select(func.count()).select_from(DimCustomer).where(DimCustomer.channel_id == channel_id),
        ),
        (
            "Sell-out",
            select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.channel_id == channel_id),
        ),
        (
            "Pricing",
            select(func.count()).select_from(FactPricing).where(FactPricing.channel_id == channel_id),
        ),
        (
            "Activation",
            select(func.count()).select_from(FactActivation).where(FactActivation.channel_id == channel_id),
        ),
        (
            "Lineup plan items",
            select(func.count())
            .select_from(FactLineupPlanItem)
            .where(FactLineupPlanItem.channel_id == channel_id),
        ),
        (
            "Historical lineup headers",
            select(func.count())
            .select_from(HistoricalLineupImportHeader)
            .where(HistoricalLineupImportHeader.channel_id == channel_id),
        ),
    ]


async def channel_hard_reference_breakdown(db: AsyncSession, channel_id: int) -> list[dict[str, int | str]]:
    row = await db.get(DimChannel, channel_id)
    if not row:
        return []
    out: list[dict[str, int | str]] = []
    for label, stmt in _hard_reference_checks(channel_id):
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out
