"""Channel delete: hard blockers (nullable FKs on masters and facts).

All reference checks execute as a single UNION ALL query.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer
from app.models.facts import FactActivation, FactPricing, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader
from app.models.import_distributor_si import ChannelSourceTokenAlias
from app.models.lineup import FactLineupPlanItem
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

# dim_product no longer carries a channel FK (channel is a go-to-market dimension of
# transactions/customers, not a product attribute) — products are not a channel-delete blocker.
_SPECS: list[tuple[str, object]] = [
    ("Customers", DimCustomer.channel_id),
    ("Sell-out", FactSalesSellout.channel_id),
    ("Pricing", FactPricing.channel_id),
    ("Activation", FactActivation.channel_id),
    ("Lineup plan items", FactLineupPlanItem.channel_id),
    ("Historical lineup headers", HistoricalLineupImportHeader.channel_id),
    ("Channel source token aliases", ChannelSourceTokenAlias.channel_id),
]


async def channel_hard_reference_breakdown_batch(
    db: AsyncSession, channel_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in channel_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out
    subqueries = [count_subquery_for_columns(label, [col], ids) for label, col in _SPECS]
    return await batch_counts_multi_table(db, subqueries, ids)


async def channel_hard_reference_breakdown(
    db: AsyncSession, channel_id: int
) -> list[dict[str, int | str]]:
    row = await db.get(DimChannel, channel_id)
    if not row:
        return []
    batch = await channel_hard_reference_breakdown_batch(db, [channel_id])
    return batch.get(channel_id, [])
