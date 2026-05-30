"""Region delete: hard blockers (nullable FKs on masters).

All reference checks execute as a single UNION ALL query.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import CustomerLocation, DimCustomer, DimRegion
from app.models.import_distributor_si import RegionSourceTokenAlias
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_SPECS: list[tuple[str, object]] = [
    ("Customers", DimCustomer.region_id),
    ("Customer locations", CustomerLocation.region_id),
    ("Region source token aliases", RegionSourceTokenAlias.region_id),
]


async def region_hard_reference_breakdown_batch(
    db: AsyncSession, region_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in region_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out
    subqueries = [count_subquery_for_columns(label, [col], ids) for label, col in _SPECS]
    return await batch_counts_multi_table(db, subqueries, ids)


async def region_hard_reference_breakdown(
    db: AsyncSession, region_id: int
) -> list[dict[str, int | str]]:
    row = await db.get(DimRegion, region_id)
    if not row:
        return []
    batch = await region_hard_reference_breakdown_batch(db, [region_id])
    return batch.get(region_id, [])
