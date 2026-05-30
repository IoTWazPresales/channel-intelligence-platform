"""Region delete: hard blockers (nullable FKs on masters)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import CustomerLocation, DimCustomer, DimRegion


def _hard_reference_checks(region_id: int) -> list[tuple[str, object]]:
    return [
        (
            "Customers",
            select(func.count()).select_from(DimCustomer).where(DimCustomer.region_id == region_id),
        ),
        (
            "Customer locations",
            select(func.count())
            .select_from(CustomerLocation)
            .where(CustomerLocation.region_id == region_id),
        ),
    ]


async def region_hard_reference_breakdown(db: AsyncSession, region_id: int) -> list[dict[str, int | str]]:
    row = await db.get(DimRegion, region_id)
    if not row:
        return []
    out: list[dict[str, int | str]] = []
    for label, stmt in _hard_reference_checks(region_id):
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out
