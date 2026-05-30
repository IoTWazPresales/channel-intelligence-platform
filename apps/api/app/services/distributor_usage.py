"""Distributor delete: hard blockers vs child rows removed with the dimension."""

from __future__ import annotations

from sqlalchemy import func, select
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
from app.services.master_usage_batch import batch_counts_for_column, merge_batch_refs

_DISTRIBUTOR_MAPPING_ENTITY_TYPES = (
    "distributor_token",
    "shipment_distributor",
)


async def _batch_mapping_candidate_counts(db: AsyncSession, distributor_ids: list[int]) -> dict[int, int]:
    ids = [int(i) for i in distributor_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    col = ImportEntityMappingCandidate.suggested_entity_id
    stmt = (
        select(col, func.count())
        .where(
            col.in_(ids),
            ImportEntityMappingCandidate.entity_type.in_(_DISTRIBUTOR_MAPPING_ENTITY_TYPES),
        )
        .group_by(col)
    )
    rows = (await db.execute(stmt)).all()
    return {int(k): int(v) for k, v in rows if k is not None}


async def distributor_hard_reference_breakdown_batch(
    db: AsyncSession, distributor_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in distributor_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out

    unassigned_rows = (
        await db.execute(
            select(DimDistributor.id).where(
                DimDistributor.id.in_(ids),
                DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE,
            )
        )
    ).scalars().all()
    for did in unassigned_rows:
        out[int(did)].append({"label": "System reference account (UNASSIGNED)", "count": 1})

    specs: list[tuple[str, object]] = [
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
    for label, col in specs:
        merge_batch_refs(out, ids, label, await batch_counts_for_column(db, col, ids))

    merge_batch_refs(
        out,
        ids,
        "Import mapping candidates (distributor)",
        await _batch_mapping_candidate_counts(db, ids),
    )
    return out


async def distributor_hard_reference_breakdown(
    db: AsyncSession, distributor_id: int
) -> list[dict[str, int | str]]:
    batch = await distributor_hard_reference_breakdown_batch(db, [distributor_id])
    return batch.get(distributor_id, [])


async def delete_distributor_children(db: AsyncSession, distributor_id: int) -> None:
    locations = (
        await db.execute(select(DistributorLocation).where(DistributorLocation.distributor_id == distributor_id))
    ).scalars().all()
    for loc in locations:
        await db.delete(loc)
    contacts = (
        await db.execute(select(DistributorContact).where(DistributorContact.distributor_id == distributor_id))
    ).scalars().all()
    for contact in contacts:
        await db.delete(contact)
