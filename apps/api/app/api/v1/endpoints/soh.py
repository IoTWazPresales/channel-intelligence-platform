"""SOH (stock on hand) and reconciliation endpoints for Channel Intelligence Platform."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.customer_sales import FactCustomerSales
from app.models.dimensions import DimDistributor, DimProduct
from app.models.facts import FactInboundShipment, FactSalesSellout

router = APIRouter()

_DATA_UNAVAILABLE_INBOUND = {"data_unavailable": True, "reason": "fact_inbound_shipment table not yet available"}
_DATA_UNAVAILABLE_SELLOUT = {"data_unavailable": True, "reason": "fact_sales_sellout table not yet available"}
_DATA_UNAVAILABLE_CUSTOMER = {"data_unavailable": True, "reason": "fact_customer_sales table not yet available"}


@router.get("/distributor")
async def distributor_soh(
    db: AsyncSession = Depends(get_db),
    product_id: int | None = None,
    distributor_id: int | None = None,
    period_from: int | None = Query(None, description="report_year * 100 + report_week, e.g. 202401"),
    period_to: int | None = Query(None, description="report_year * 100 + report_week, e.g. 202452"),
) -> dict[str, Any]:
    """Distributor SOH per product per week: cumulative inbound minus cumulative sell-out."""
    try:
        inbound_q = select(
            FactInboundShipment.product_id,
            DimProduct.sku.label("product_sku"),
            FactInboundShipment.distributor_id,
            DimDistributor.code.label("distributor_code"),
            func.sum(FactInboundShipment.quantity).label("cumulative_inbound"),
        ).outerjoin(
            DimProduct, FactInboundShipment.product_id == DimProduct.id
        ).outerjoin(
            DimDistributor, FactInboundShipment.distributor_id == DimDistributor.id
        ).where(
            FactInboundShipment.status == "received",
        )

        if product_id is not None:
            inbound_q = inbound_q.where(FactInboundShipment.product_id == int(product_id))
        if distributor_id is not None:
            inbound_q = inbound_q.where(FactInboundShipment.distributor_id == int(distributor_id))

        inbound_q = inbound_q.group_by(
            FactInboundShipment.product_id,
            DimProduct.sku,
            FactInboundShipment.distributor_id,
            DimDistributor.code,
        )
        inbound_rows = (await db.execute(inbound_q)).all()

        sellout_q = select(
            FactSalesSellout.product_id,
            FactSalesSellout.distributor_id,
            func.sum(FactSalesSellout.units).label("cumulative_sellout"),
        )
        if product_id is not None:
            sellout_q = sellout_q.where(FactSalesSellout.product_id == int(product_id))
        if distributor_id is not None:
            sellout_q = sellout_q.where(FactSalesSellout.distributor_id == int(distributor_id))
        sellout_q = sellout_q.group_by(FactSalesSellout.product_id, FactSalesSellout.distributor_id)
        sellout_rows = (await db.execute(sellout_q)).all()

        sellout_map: dict[tuple[int | None, int | None], float] = {}
        for sr in sellout_rows:
            sellout_map[(sr.product_id, sr.distributor_id)] = float(sr.cumulative_sellout or 0)

        items: list[dict[str, Any]] = []
        for r in inbound_rows:
            cum_in = float(r.cumulative_inbound or 0)
            cum_out = sellout_map.get((r.product_id, r.distributor_id), 0.0)
            items.append({
                "product_id": r.product_id,
                "product_sku": r.product_sku,
                "distributor_id": r.distributor_id,
                "distributor_code": r.distributor_code,
                "cumulative_inbound": cum_in,
                "cumulative_sellout": cum_out,
                "calculated_soh": cum_in - cum_out,
            })

    except Exception:
        return {**_DATA_UNAVAILABLE_INBOUND, "items": []}

    return {"data_unavailable": False, "items": items}


@router.get("/retailer")
async def retailer_soh(
    db: AsyncSession = Depends(get_db),
    product_id: int | None = None,
    customer_id: int | None = None,
) -> dict[str, Any]:
    """Retailer SOH: cumulative distributor sell-out to customer minus cumulative customer sell-out."""
    try:
        dist_sellout_q = select(
            FactSalesSellout.product_id,
            DimProduct.sku.label("product_sku"),
            FactSalesSellout.customer_id,
            func.sum(FactSalesSellout.units).label("cumulative_dist_sellout"),
        ).outerjoin(
            DimProduct, FactSalesSellout.product_id == DimProduct.id
        )
        if product_id is not None:
            dist_sellout_q = dist_sellout_q.where(FactSalesSellout.product_id == int(product_id))
        if customer_id is not None:
            dist_sellout_q = dist_sellout_q.where(FactSalesSellout.customer_id == int(customer_id))
        dist_sellout_q = dist_sellout_q.group_by(
            FactSalesSellout.product_id, DimProduct.sku, FactSalesSellout.customer_id
        )
        dist_rows = (await db.execute(dist_sellout_q)).all()

        cust_sellout_q = select(
            FactCustomerSales.product_id,
            FactCustomerSales.customer_id,
            func.sum(FactCustomerSales.quantity_sold).label("cumulative_cust_sellout"),
        )
        if product_id is not None:
            cust_sellout_q = cust_sellout_q.where(FactCustomerSales.product_id == int(product_id))
        if customer_id is not None:
            cust_sellout_q = cust_sellout_q.where(FactCustomerSales.customer_id == int(customer_id))
        cust_sellout_q = cust_sellout_q.group_by(
            FactCustomerSales.product_id, FactCustomerSales.customer_id
        )
        cust_rows = (await db.execute(cust_sellout_q)).all()

        cust_map: dict[tuple[int | None, int | None], float] = {}
        for cr in cust_rows:
            cust_map[(cr.product_id, cr.customer_id)] = float(cr.cumulative_cust_sellout or 0)

        items: list[dict[str, Any]] = []
        for r in dist_rows:
            cum_in = float(r.cumulative_dist_sellout or 0)
            cum_out = cust_map.get((r.product_id, r.customer_id), 0.0)
            items.append({
                "product_id": r.product_id,
                "product_sku": r.product_sku,
                "customer_id": r.customer_id,
                "cumulative_dist_sellout": cum_in,
                "cumulative_cust_sellout": cum_out,
                "calculated_retailer_soh": cum_in - cum_out,
            })

    except Exception:
        return {**_DATA_UNAVAILABLE_SELLOUT, "items": []}

    return {"data_unavailable": False, "items": items}


@router.get("/journey")
async def stock_journey(
    db: AsyncSession = Depends(get_db),
    product_id: int | None = None,
) -> dict[str, Any]:
    """Per product pipeline: in_transit, at_distributor, at_retailer, sold, total_pipeline."""
    try:
        in_transit_q = select(
            FactInboundShipment.product_id,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0).label("in_transit"),
        ).where(FactInboundShipment.status == "scheduled")
        if product_id is not None:
            in_transit_q = in_transit_q.where(FactInboundShipment.product_id == int(product_id))
        in_transit_q = in_transit_q.group_by(FactInboundShipment.product_id)
        in_transit_rows = {r.product_id: float(r.in_transit) for r in (await db.execute(in_transit_q)).all()}

        received_q = select(
            FactInboundShipment.product_id,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0).label("received"),
        ).where(FactInboundShipment.status == "received")
        if product_id is not None:
            received_q = received_q.where(FactInboundShipment.product_id == int(product_id))
        received_q = received_q.group_by(FactInboundShipment.product_id)
        received_rows = {r.product_id: float(r.received) for r in (await db.execute(received_q)).all()}

        sellout_q = select(
            FactSalesSellout.product_id,
            func.coalesce(func.sum(FactSalesSellout.units), 0).label("dist_sold"),
        )
        if product_id is not None:
            sellout_q = sellout_q.where(FactSalesSellout.product_id == int(product_id))
        sellout_q = sellout_q.group_by(FactSalesSellout.product_id)
        sellout_rows = {r.product_id: float(r.dist_sold) for r in (await db.execute(sellout_q)).all()}

        cust_q = select(
            FactCustomerSales.product_id,
            func.coalesce(func.sum(FactCustomerSales.quantity_sold), 0).label("cust_sold"),
        )
        if product_id is not None:
            cust_q = cust_q.where(FactCustomerSales.product_id == int(product_id))
        cust_q = cust_q.group_by(FactCustomerSales.product_id)
        cust_sold_rows = {r.product_id: float(r.cust_sold) for r in (await db.execute(cust_q)).all()}

        all_pids = set(in_transit_rows) | set(received_rows) | set(sellout_rows) | set(cust_sold_rows)
        if product_id is not None:
            all_pids = {product_id} if product_id in all_pids else set()

        items: list[dict[str, Any]] = []
        for pid in sorted(all_pids):
            in_t = in_transit_rows.get(pid, 0.0)
            received = received_rows.get(pid, 0.0)
            dist_sold = sellout_rows.get(pid, 0.0)
            cust_sold = cust_sold_rows.get(pid, 0.0)
            at_distributor = received - dist_sold
            at_retailer = dist_sold - cust_sold
            items.append({
                "product_id": pid,
                "in_transit": in_t,
                "at_distributor": max(at_distributor, 0.0),
                "at_retailer": max(at_retailer, 0.0),
                "sold": cust_sold,
                "total_pipeline": in_t + max(at_distributor, 0.0) + max(at_retailer, 0.0),
            })

    except Exception:
        return {"data_unavailable": True, "reason": "One or more fact tables not yet available", "items": []}

    return {"data_unavailable": False, "items": items}


@router.get("/reconciliation/gaps")
async def reconciliation_gaps(
    db: AsyncSession = Depends(get_db),
    product_id: int | None = None,
) -> dict[str, Any]:
    """Reported vs calculated SOH gaps, unaccounted stock, sell_through_rate per product."""
    try:
        received_q = select(
            FactInboundShipment.product_id,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0).label("total_received"),
        ).where(FactInboundShipment.status == "received")
        if product_id is not None:
            received_q = received_q.where(FactInboundShipment.product_id == int(product_id))
        received_q = received_q.group_by(FactInboundShipment.product_id)
        received_map = {r.product_id: float(r.total_received) for r in (await db.execute(received_q)).all()}

        sellout_q = select(
            FactSalesSellout.product_id,
            func.coalesce(func.sum(FactSalesSellout.units), 0).label("total_sellout"),
        )
        if product_id is not None:
            sellout_q = sellout_q.where(FactSalesSellout.product_id == int(product_id))
        sellout_q = sellout_q.group_by(FactSalesSellout.product_id)
        sellout_map = {r.product_id: float(r.total_sellout) for r in (await db.execute(sellout_q)).all()}

        reported_soh_q = select(
            FactCustomerSales.product_id,
            func.max(FactCustomerSales.reported_soh).label("latest_reported_soh"),
        ).where(FactCustomerSales.reported_soh.is_not(None))
        if product_id is not None:
            reported_soh_q = reported_soh_q.where(FactCustomerSales.product_id == int(product_id))
        reported_soh_q = reported_soh_q.group_by(FactCustomerSales.product_id)
        reported_map = {r.product_id: float(r.latest_reported_soh) for r in (await db.execute(reported_soh_q)).all()}

        all_pids = set(received_map) | set(sellout_map) | set(reported_map)
        items: list[dict[str, Any]] = []
        for pid in sorted(all_pids):
            total_in = received_map.get(pid, 0.0)
            total_out = sellout_map.get(pid, 0.0)
            calculated_soh = total_in - total_out
            reported_soh = reported_map.get(pid)
            gap = (reported_soh - calculated_soh) if reported_soh is not None else None
            sell_through = (total_out / total_in) if total_in > 0 else 0.0
            items.append({
                "product_id": pid,
                "total_received": total_in,
                "total_sellout": total_out,
                "calculated_soh": calculated_soh,
                "reported_soh": reported_soh,
                "gap": gap,
                "unaccounted_stock": gap if gap is not None and gap != 0 else None,
                "sell_through_rate": round(sell_through, 4),
            })

    except Exception:
        return {"data_unavailable": True, "reason": "One or more fact tables not yet available", "items": []}

    return {"data_unavailable": False, "items": items}
