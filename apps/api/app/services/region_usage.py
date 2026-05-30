"""Region delete: hard blockers (nullable FKs on masters)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import CustomerLocation, DimCustomer, DimRegion
from app.models.import_distributor_si import RegionSourceTokenAlias
from app.services.master_usage_batch import batch_counts_for_column, merge_batch_refs


async def region_hard_reference_breakdown_batch(
    db: AsyncSession, region_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in region_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out

    specs: list[tuple[str, object]] = [
        ("Customers", DimCustomer.region_id),
        ("Customer locations", CustomerLocation.region_id),
        ("Region source token aliases", RegionSourceTokenAlias.region_id),
    ]
    for label, col in specs:
        merge_batch_refs(out, ids, label, await batch_counts_for_column(db, col, ids))
    return out


async def region_hard_reference_breakdown(db: AsyncSession, region_id: int) -> list[dict[str, int | str]]:
    row = await db.get(DimRegion, region_id)
    if not row:
        return []
    batch = await region_hard_reference_breakdown_batch(db, [region_id])
    return batch.get(region_id, [])
