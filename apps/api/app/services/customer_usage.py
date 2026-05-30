"""Customer delete: hard blockers vs derived rows that are auto-cleaned."""

from __future__ import annotations

from sqlalchemy import delete, func, select
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
    FactForecast,
    FactInventoryCustomer,
    FactInventoryReconciliation,
    FactPricing,
    FactReturns,
    FactSalesSellout,
)
from app.models.historical_lineup import HistoricalLineupImportHeader
from app.models.lineup import FactLineupPlanItem
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE


def _hard_reference_checks(customer_id: int) -> list[tuple[str, object]]:
    return [
        (
            "Sell-out",
            select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.customer_id == customer_id),
        ),
        (
            "Returns",
            select(func.count()).select_from(FactReturns).where(FactReturns.customer_id == customer_id),
        ),
        (
            "Customer inventory",
            select(func.count())
            .select_from(FactInventoryCustomer)
            .where(FactInventoryCustomer.customer_id == customer_id),
        ),
        (
            "Inventory reconciliation",
            select(func.count())
            .select_from(FactInventoryReconciliation)
            .where(FactInventoryReconciliation.customer_id == customer_id),
        ),
        (
            "Customer sell-through",
            select(func.count())
            .select_from(FactCustomerSellthrough)
            .where(FactCustomerSellthrough.customer_id == customer_id),
        ),
        (
            "Customer velocity",
            select(func.count())
            .select_from(FactCustomerVelocity)
            .where(FactCustomerVelocity.customer_id == customer_id),
        ),
        (
            "Pricing (customer-specific)",
            select(func.count()).select_from(FactPricing).where(FactPricing.customer_id == customer_id),
        ),
        (
            "Forecasts",
            select(func.count()).select_from(FactForecast).where(FactForecast.customer_id == customer_id),
        ),
        (
            "Lineup plan items",
            select(func.count())
            .select_from(FactLineupPlanItem)
            .where(FactLineupPlanItem.customer_id == customer_id),
        ),
        (
            "Commercial customer terms",
            select(func.count())
            .select_from(CommercialCustomerTerm)
            .where(CommercialCustomerTerm.customer_id == customer_id),
        ),
        (
            "Commercial plan lines",
            select(func.count())
            .select_from(CommercialPlanLine)
            .where(CommercialPlanLine.customer_id == customer_id),
        ),
        (
            "Commercial lineup lines",
            select(func.count())
            .select_from(CommercialLineupLine)
            .where(CommercialLineupLine.customer_id == customer_id),
        ),
        (
            "Historical lineup headers",
            select(func.count())
            .select_from(HistoricalLineupImportHeader)
            .where(HistoricalLineupImportHeader.customer_id == customer_id),
        ),
        (
            "Shipment evidence (resolved customer)",
            select(func.count())
            .select_from(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.customer_id == customer_id),
        ),
        (
            "Customer report config",
            select(func.count())
            .select_from(CustomerReportConfig)
            .where(CustomerReportConfig.customer_id == customer_id),
        ),
    ]


async def customer_hard_reference_breakdown(db: AsyncSession, customer_id: int) -> list[dict[str, int | str]]:
    row = await db.get(DimCustomer, customer_id)
    if row and row.code == OPEN_CHANNEL_CUSTOMER_CODE:
        return [{"label": "System reference account (OPEN_CHANNEL)", "count": 1}]
    out: list[dict[str, int | str]] = []
    for label, stmt in _hard_reference_checks(customer_id):
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out


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
