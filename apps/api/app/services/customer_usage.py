"""Customer delete: hard blockers vs derived rows that are auto-cleaned.

All hard-reference checks are executed as a single UNION ALL query — one
network round trip to the database regardless of the number of tables checked.
"""

from __future__ import annotations

from sqlalchemy import Select, delete, func, literal, select
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
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_CUSTOMER_MAPPING_ENTITY_TYPES = (
    "customer_dealer_token",
    "shipment_customer_token",
)

# Ordered spec list: (display label, FK column).
# Each entry becomes one subquery in the UNION ALL reference check.
_SPECS: list[tuple[str, object]] = [
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


def _extra_customer_subqueries(ids: list[int]) -> list[Select]:
    """Additional subqueries with non-standard WHERE clauses included in the UNION ALL."""
    return [
        # Flag the system-reserved OPEN_CHANNEL record as undeletable.
        select(
            literal("System reference account (OPEN_CHANNEL)").label("lbl"),
            DimCustomer.id.label("entity_id"),
            literal(1).label("cnt"),
        ).where(DimCustomer.id.in_(ids), DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE),
        # Mapping candidates restricted to customer entity types.
        select(
            literal("Import mapping candidates (customer)").label("lbl"),
            ImportEntityMappingCandidate.suggested_entity_id.label("entity_id"),
            func.count().label("cnt"),
        )
        .where(
            ImportEntityMappingCandidate.suggested_entity_id.in_(ids),
            ImportEntityMappingCandidate.entity_type.in_(_CUSTOMER_MAPPING_ENTITY_TYPES),
        )
        .group_by(ImportEntityMappingCandidate.suggested_entity_id),
    ]


async def customer_hard_reference_breakdown_batch(
    db: AsyncSession, customer_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in customer_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out
    subqueries = [count_subquery_for_columns(label, [col], ids) for label, col in _SPECS]
    subqueries.extend(_extra_customer_subqueries(ids))
    return await batch_counts_multi_table(db, subqueries, ids)


async def customer_hard_reference_breakdown(
    db: AsyncSession, customer_id: int
) -> list[dict[str, int | str]]:
    batch = await customer_hard_reference_breakdown_batch(db, [customer_id])
    return batch.get(customer_id, [])


async def cleanup_soft_customer_references(db: AsyncSession, customer_id: int) -> None:
    await db.execute(delete(StockRisk).where(StockRisk.customer_id == customer_id))
    await db.execute(delete(WeeksOfStock).where(WeeksOfStock.customer_id == customer_id))
    await db.execute(delete(StockHealth).where(StockHealth.customer_id == customer_id))


async def delete_customer_children(db: AsyncSession, customer_id: int) -> None:
    await db.execute(delete(CustomerLocation).where(CustomerLocation.customer_id == customer_id))
    await db.execute(delete(CustomerContact).where(CustomerContact.customer_id == customer_id))
