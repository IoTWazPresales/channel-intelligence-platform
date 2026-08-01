"""Customer delete: hard blockers vs derived rows that are auto-cleaned.

All hard-reference checks are executed as a single UNION ALL query — one
network round trip to the database regardless of the number of tables checked.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Select, cast, delete, func, literal, select
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
from app.models.fact_demand_forecast import FactDemandForecast
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
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)

EV = shipment_evidence_read_model()
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_CUSTOMER_MAPPING_ENTITY_TYPES = (
    "customer_dealer_token",
    "shipment_customer_token",
)

DSI_STAGING_REF_LABEL = "DSI import staging (resolved customer)"

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
    ("Forecasts (legacy)", FactForecast.customer_id),
    ("Demand forecasts", FactDemandForecast.customer_id),
    ("Lineup plan items", FactLineupPlanItem.customer_id),
    ("Commercial customer terms", CommercialCustomerTerm.customer_id),
    ("Commercial plan lines", CommercialPlanLine.customer_id),
    ("Commercial lineup lines", CommercialLineupLine.customer_id),
    ("Historical lineup headers", HistoricalLineupImportHeader.customer_id),
    ("Shipment evidence (resolved customer)", EV.customer_id),
    ("Customer report config", CustomerReportConfig.customer_id),
    (DSI_STAGING_REF_LABEL, ImportDistributorSiStagingLine.resolved_customer_id),
    ("Customer sell-through import staging", ImportCustomerSellthroughStagingLine.resolved_customer_id),
    ("Customer source token aliases", CustomerSourceTokenAlias.customer_id),
    ("Budget requests (linked customer)", FactBudgetRequest.linked_customer_id),
]


def _extra_customer_subqueries(ids: list[int]) -> list[Select]:
    """Additional subqueries with non-standard WHERE clauses included in the UNION ALL."""
    cnt_one = cast(literal(1), BigInteger).label("cnt")
    return [
        # Flag the system-reserved OPEN_CHANNEL record as undeletable.
        select(
            literal("System reference account (OPEN_CHANNEL)").label("lbl"),
            DimCustomer.id.label("entity_id"),
            cnt_one,
        ).where(DimCustomer.id.in_(ids), DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE),
        # Mapping candidates restricted to customer entity types.
        select(
            literal("Import mapping candidates (customer)").label("lbl"),
            ImportEntityMappingCandidate.suggested_entity_id.label("entity_id"),
            cast(func.count(), BigInteger).label("cnt"),
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
    subqueries = []
    for label, col in _SPECS:
        sq = count_subquery_for_columns(label, [col], ids)
        if label.startswith("Shipment evidence"):
            sq = apply_active_evidence_filter(sq, model=EV)
        subqueries.append(sq)
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
    """Remove child rows before dim_customer delete (aliases also CASCADE at DB level)."""
    await db.execute(
        delete(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.customer_id == customer_id)
    )
    await db.execute(delete(CustomerLocation).where(CustomerLocation.customer_id == customer_id))
    await db.execute(delete(CustomerContact).where(CustomerContact.customer_id == customer_id))
