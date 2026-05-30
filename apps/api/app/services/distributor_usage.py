"""Distributor delete: hard blockers vs child rows removed with the dimension."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase
from app.models.commercial_planner import CommercialDistributorTerm, CommercialPlanLine
from app.models.dimensions import DimCustomer, DimDistributor, DistributorContact, DistributorLocation
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
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE


def _hard_reference_checks(distributor_id: int) -> list[tuple[str, object]]:
    return [
        (
            "Sell-in",
            select(func.count()).select_from(FactSalesSellin).where(FactSalesSellin.distributor_id == distributor_id),
        ),
        (
            "Sell-out",
            select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.distributor_id == distributor_id),
        ),
        (
            "Returns",
            select(func.count()).select_from(FactReturns).where(FactReturns.distributor_id == distributor_id),
        ),
        (
            "Distributor inventory",
            select(func.count())
            .select_from(FactInventoryDistributor)
            .where(FactInventoryDistributor.distributor_id == distributor_id),
        ),
        (
            "Inventory reconciliation",
            select(func.count())
            .select_from(FactInventoryReconciliation)
            .where(FactInventoryReconciliation.distributor_id == distributor_id),
        ),
        (
            "Inbound shipments",
            select(func.count())
            .select_from(FactInboundShipment)
            .where(FactInboundShipment.distributor_id == distributor_id),
        ),
        (
            "Buy plans",
            select(func.count()).select_from(FactBuyPlan).where(FactBuyPlan.distributor_id == distributor_id),
        ),
        (
            "DSI forecasts",
            select(func.count()).select_from(FactDsiForecast).where(FactDsiForecast.distributor_id == distributor_id),
        ),
        (
            "Commercial distributor terms",
            select(func.count())
            .select_from(CommercialDistributorTerm)
            .where(CommercialDistributorTerm.distributor_id == distributor_id),
        ),
        (
            "Commercial plan lines",
            select(func.count())
            .select_from(CommercialPlanLine)
            .where(CommercialPlanLine.distributor_id == distributor_id),
        ),
        (
            "Commercial lineup cases",
            select(func.count())
            .select_from(CommercialLineupCase)
            .where(CommercialLineupCase.distributor_id == distributor_id),
        ),
        (
            "Historical lineup headers",
            select(func.count())
            .select_from(HistoricalLineupImportHeader)
            .where(HistoricalLineupImportHeader.distributor_id == distributor_id),
        ),
        (
            "Shipment evidence (resolved distributor)",
            select(func.count())
            .select_from(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.distributor_id == distributor_id),
        ),
        (
            "Customers with preferred distributor",
            select(func.count())
            .select_from(DimCustomer)
            .where(DimCustomer.preferred_distributor_id == distributor_id),
        ),
    ]


async def distributor_hard_reference_breakdown(
    db: AsyncSession, distributor_id: int
) -> list[dict[str, int | str]]:
    row = await db.get(DimDistributor, distributor_id)
    if row and row.code == UNASSIGNED_DISTRIBUTOR_CODE:
        return [{"label": "System reference account (UNASSIGNED)", "count": 1}]
    out: list[dict[str, int | str]] = []
    for label, stmt in _hard_reference_checks(distributor_id):
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out


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
