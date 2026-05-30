"""Customer delete: hard blockers vs derived rows that are auto-cleaned."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine
from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialPlanLine,
)
from app.models.customer_report_config import CustomerReportConfig
from app.models.derived import StockHealth, StockRisk, WeeksOfStock
from app.models.dimensions import CustomerContact, CustomerLocation, DimCustomer
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.facts import (
    FactBudgetRequest,
    FactForecast,
    FactInventoryCustomer,
    FactInventoryReconciliation,
    FactPricing,
    FactReturns,
    FactSalesSellout,
)
from app.models.historical_lineup import HistoricalLineupImportHeader
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.lineup import FactLineupPlanItem
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.master_usage_batch import batch_counts_for_column, merge_batch_refs

_CUSTOMER_MAPPING_ENTITY_TYPES = (
    "customer_dealer_token",
    "shipment_customer_token",
)


async def _batch_mapping_candidate_counts(db: AsyncSession, customer_ids: list[int]) -> dict[int, int]:
    ids = [int(i) for i in customer_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    col = ImportEntityMappingCandidate.suggested_entity_id
    stmt = (
        select(col, func.count())
        .where(
            col.in_(ids),
            ImportEntityMappingCandidate.entity_type.in_(_CUSTOMER_MAPPING_ENTITY_TYPES),
        )
        .group_by(col)
    )
    rows = (await db.execute(stmt)).all()
    return {int(k): int(v) for k, v in rows if k is not None}


async def customer_hard_reference_breakdown_batch(
    db: AsyncSession, customer_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in customer_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out

    open_rows = (
        await db.execute(
            select(DimCustomer.id).where(
                DimCustomer.id.in_(ids),
                DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE,
            )
        )
    ).scalars().all()
    for cid in open_rows:
        out[int(cid)].append({"label": "System reference account (OPEN_CHANNEL)", "count": 1})

    specs: list[tuple[str, object]] = [
        ("Sell-out", FactSalesSellout.customer_id),
        ("Returns", FactReturns.customer_id),
        ("Customer inventory", FactInventoryCustomer.customer_id),
        ("Inventory reconciliation", FactInventoryReconciliation.customer_id),
        ("Customer sell-through", FactCustomerSellthrough.customer_id),
        ("Customer velocity", FactCustomerVelocity.customer_id),
        ("Pricing (customer-specific)", FactPricing.customer_id),
        ("Forecasts", FactForecast.customer_id),
        ("Lineup plan items", FactLineupPlanItem.customer_id),
        ("Commercial customer terms", CommercialCustomerTerm.customer_id),
        ("Commercial plan lines", CommercialPlanLine.customer_id),
        ("Commercial lineup lines", CommercialLineupLine.customer_id),
        ("Historical lineup headers", HistoricalLineupImportHeader.customer_id),
        ("Shipment evidence (resolved customer)", ShipmentEvidenceLine.customer_id),
        ("Customer report config", CustomerReportConfig.customer_id),
        ("DSI import staging (resolved customer)", ImportDistributorSiStagingLine.resolved_customer_id),
        ("Customer sell-through import staging", ImportCustomerSellthroughStagingLine.resolved_customer_id),
        ("Customer source token aliases", CustomerSourceTokenAlias.customer_id),
        ("Budget requests (linked customer)", FactBudgetRequest.linked_customer_id),
    ]
    for label, col in specs:
        merge_batch_refs(out, ids, label, await batch_counts_for_column(db, col, ids))

    merge_batch_refs(
        out,
        ids,
        "Import mapping candidates (customer)",
        await _batch_mapping_candidate_counts(db, ids),
    )
    return out


async def customer_hard_reference_breakdown(db: AsyncSession, customer_id: int) -> list[dict[str, int | str]]:
    batch = await customer_hard_reference_breakdown_batch(db, [customer_id])
    return batch.get(customer_id, [])


async def cleanup_soft_customer_references(db: AsyncSession, customer_id: int) -> None:
    await db.execute(delete(StockRisk).where(StockRisk.customer_id == customer_id))
    await db.execute(delete(WeeksOfStock).where(WeeksOfStock.customer_id == customer_id))
    await db.execute(delete(StockHealth).where(StockHealth.customer_id == customer_id))


async def delete_customer_children(db: AsyncSession, customer_id: int) -> None:
    locations = (
        await db.execute(select(CustomerLocation).where(CustomerLocation.customer_id == customer_id))
    ).scalars().all()
    for loc in locations:
        await db.delete(loc)
    contacts = (
        await db.execute(select(CustomerContact).where(CustomerContact.customer_id == customer_id))
    ).scalars().all()
    for contact in contacts:
        await db.delete(contact)
