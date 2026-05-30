"""Customer location delete: hard blockers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine


def _hard_reference_checks(location_id: int) -> list[tuple[str, object]]:
    return [
        (
            "Customer sell-through",
            select(func.count())
            .select_from(FactCustomerSellthrough)
            .where(FactCustomerSellthrough.customer_location_id == location_id),
        ),
        (
            "Sell-through import staging",
            select(func.count())
            .select_from(ImportCustomerSellthroughStagingLine)
            .where(ImportCustomerSellthroughStagingLine.resolved_location_id == location_id),
        ),
    ]


async def customer_location_hard_reference_breakdown(
    db: AsyncSession, location_id: int
) -> list[dict[str, int | str]]:
    out: list[dict[str, int | str]] = []
    for label, stmt in _hard_reference_checks(location_id):
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out
