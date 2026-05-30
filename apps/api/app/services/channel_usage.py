"""Channel delete: hard blockers (nullable FKs on masters and facts)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimProduct
from app.models.facts import FactActivation, FactPricing, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader
from app.models.import_distributor_si import ChannelSourceTokenAlias
from app.models.lineup import FactLineupPlanItem
from app.services.master_usage_batch import batch_counts_for_column, merge_batch_refs


async def channel_hard_reference_breakdown_batch(
    db: AsyncSession, channel_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in channel_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out

    specs: list[tuple[str, object]] = [
        ("Products (primary channel)", DimProduct.channel_id),
        ("Customers", DimCustomer.channel_id),
        ("Sell-out", FactSalesSellout.channel_id),
        ("Pricing", FactPricing.channel_id),
        ("Activation", FactActivation.channel_id),
        ("Lineup plan items", FactLineupPlanItem.channel_id),
        ("Historical lineup headers", HistoricalLineupImportHeader.channel_id),
        ("Channel source token aliases", ChannelSourceTokenAlias.channel_id),
    ]
    for label, col in specs:
        merge_batch_refs(out, ids, label, await batch_counts_for_column(db, col, ids))
    return out


async def channel_hard_reference_breakdown(db: AsyncSession, channel_id: int) -> list[dict[str, int | str]]:
    row = await db.get(DimChannel, channel_id)
    if not row:
        return []
    batch = await channel_hard_reference_breakdown_batch(db, [channel_id])
    return batch.get(channel_id, [])
