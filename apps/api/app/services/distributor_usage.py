"""Distributor delete: hard blockers vs child rows removed with the dimension.

All hard-reference checks are executed as a single UNION ALL query — one
network round trip to the database regardless of the number of tables checked.
"""

from __future__ import annotations

from sqlalchemy import Select, delete, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine
from app.models.commercial_planner import CommercialDistributorTerm, CommercialPlanLine
from app.models.dimensions import DimCustomer, DimDistributor, DistributorContact, DistributorLocation
from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.fact_dsi_forecast import FactDsiForecast
from app.models.facts import (
    FactBuyPlan,
    FactInboundShipment,
    FactInventoryDistributor,
    FactInventoryReconciliation,
    FactReturns,
    FactSalesSellin,
    FactSalesSellout,
)
from app.models.historical_lineup import HistoricalLineupImportHeader
from app.models.import_distributor_si import (
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_DISTRIBUTOR_MAPPING_ENTITY_TYPES = (
    "distributor_token",
    "shipment_distributor",
)

_SPECS: list[tuple[str, object]] = [
    ("Sell-in", FactSalesSellin.distributor_id),
    ("Sell-out", FactSalesSellout.distributor_id),
    ("Returns", FactReturns.distributor_id),
    ("Distributor inventory", FactInventoryDistributor.distributor_id),
    ("Inventory reconciliation", FactInventoryReconciliation.distributor_id),
    ("Inbound shipments", FactInboundShipment.distributor_id),
    ("Buy plans", FactBuyPlan.distributor_id),
    ("DSI forecasts", FactDsiForecast.distributor_id),
    ("Customer velocity", FactCustomerVelocity.distributor_id),
    ("Commercial distributor terms", CommercialDistributorTerm.distributor_id),
    ("Commercial plan lines", CommercialPlanLine.distributor_id),
    ("Commercial lineup lines", CommercialLineupLine.distributor_id),
    ("Historical lineup headers", HistoricalLineupImportHeader.distributor_id),
    ("Shipment evidence (resolved distributor)", ShipmentEvidenceLine.distributor_id),
    ("Customers with preferred distributor", DimCustomer.preferred_distributor_id),
    ("DSI import staging (resolved distributor)", ImportDistributorSiStagingLine.resolved_distributor_id),
    ("Distributor source token aliases", DistributorSourceTokenAlias.distributor_id),
]


def _extra_distributor_subqueries(ids: list[int]) -> list[Select]:
    """Additional subqueries with non-standard WHERE clauses included in the UNION ALL."""
    return [
        # Flag the system-reserved UNASSIGNED record as undeletable.
        select(
            literal("System reference account (UNASSIGNED)").label("lbl"),
            DimDistributor.id.label("entity_id"),
            literal(1).label("cnt"),
        ).where(DimDistributor.id.in_(ids), DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE),
        # Mapping candidates restricted to distributor entity types.
        select(
            literal("Import mapping candidates (distributor)").label("lbl"),
            ImportEntityMappingCandidate.suggested_entity_id.label("entity_id"),
            func.count().label("cnt"),
        )
        .where(
            ImportEntityMappingCandidate.suggested_entity_id.in_(ids),
            ImportEntityMappingCandidate.entity_type.in_(_DISTRIBUTOR_MAPPING_ENTITY_TYPES),
        )
        .group_by(ImportEntityMappingCandidate.suggested_entity_id),
    ]


async def distributor_hard_reference_breakdown_batch(
    db: AsyncSession, distributor_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in distributor_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out
    subqueries = [count_subquery_for_columns(label, [col], ids) for label, col in _SPECS]
    subqueries.extend(_extra_distributor_subqueries(ids))
    return await batch_counts_multi_table(db, subqueries, ids)


async def distributor_hard_reference_breakdown(
    db: AsyncSession, distributor_id: int
) -> list[dict[str, int | str]]:
    batch = await distributor_hard_reference_breakdown_batch(db, [distributor_id])
    return batch.get(distributor_id, [])


async def delete_distributor_children(db: AsyncSession, distributor_id: int) -> None:
    await db.execute(
        delete(DistributorLocation).where(DistributorLocation.distributor_id == distributor_id)
    )
    await db.execute(
        delete(DistributorContact).where(DistributorContact.distributor_id == distributor_id)
    )
