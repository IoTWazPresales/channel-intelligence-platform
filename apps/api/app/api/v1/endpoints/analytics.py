"""Analytics endpoints for buy planning, promotion planning, and pipeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.customer_sales import FactCustomerSales
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactInboundShipment, FactSalesSellout

router = APIRouter()


@router.get("/buy-plan-signals")
async def buy_plan_signals(
    db: AsyncSession = Depends(get_db),
    product_id: int | None = None,
    customer_id: int | None = None,
    weeks_lookback: int = Query(4, ge=1, le=52),
) -> dict[str, Any]:
    """Per product per retailer: rolling average sell-through, weeks_of_cover, reorder_signal."""
    try:
        sellout_q = select(
            FactCustomerSales.product_id,
            DimProduct.sku.label("product_sku"),
            DimProduct.name.label("product_name"),
            FactCustomerSales.customer_id,
            DimCustomer.code.label("customer_code"),
            DimCustomer.name.label("customer_name"),
            func.sum(FactCustomerSales.quantity_sold).label("total_sold"),
            func.count(func.distinct(
                func.concat(FactCustomerSales.report_year, '-', FactCustomerSales.report_week)
            )).label("weeks_active"),
        ).outerjoin(
            DimProduct, FactCustomerSales.product_id == DimProduct.id
        ).outerjoin(
            DimCustomer, FactCustomerSales.customer_id == DimCustomer.id
        ).where(
            FactCustomerSales.product_id.is_not(None),
            FactCustomerSales.customer_id.is_not(None),
        )

        if product_id is not None:
            sellout_q = sellout_q.where(FactCustomerSales.product_id == int(product_id))
        if customer_id is not None:
            sellout_q = sellout_q.where(FactCustomerSales.customer_id == int(customer_id))

        sellout_q = sellout_q.group_by(
            FactCustomerSales.product_id,
            DimProduct.sku,
            DimProduct.name,
            FactCustomerSales.customer_id,
            DimCustomer.code,
            DimCustomer.name,
        )
        rows = (await db.execute(sellout_q)).all()

        received_q = select(
            FactInboundShipment.product_id,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0).label("total_received"),
        ).where(FactInboundShipment.status == "received")
        if product_id is not None:
            received_q = received_q.where(FactInboundShipment.product_id == int(product_id))
        received_q = received_q.group_by(FactInboundShipment.product_id)
        received_map = {r.product_id: float(r.total_received) for r in (await db.execute(received_q)).all()}

        dist_sellout_q = select(
            FactSalesSellout.product_id,
            func.coalesce(func.sum(FactSalesSellout.units), 0).label("total_dist_sold"),
        )
        if product_id is not None:
            dist_sellout_q = dist_sellout_q.where(FactSalesSellout.product_id == int(product_id))
        dist_sellout_q = dist_sellout_q.group_by(FactSalesSellout.product_id)
        dist_sold_map = {r.product_id: float(r.total_dist_sold) for r in (await db.execute(dist_sellout_q)).all()}

        items: list[dict[str, Any]] = []
        for r in rows:
            total_sold = float(r.total_sold or 0)
            weeks_active = int(r.weeks_active or 1)
            avg_weekly = total_sold / max(weeks_active, 1)

            stock_at_dist = received_map.get(r.product_id, 0.0) - dist_sold_map.get(r.product_id, 0.0)
            weeks_of_cover = (stock_at_dist / avg_weekly) if avg_weekly > 0 else None
            reorder_signal = weeks_of_cover is not None and weeks_of_cover < weeks_lookback

            items.append({
                "product_id": r.product_id,
                "product_sku": r.product_sku,
                "product_name": r.product_name,
                "customer_id": r.customer_id,
                "customer_code": r.customer_code,
                "customer_name": r.customer_name,
                "total_sold_units": total_sold,
                "weeks_active": weeks_active,
                "avg_weekly_sellthrough": round(avg_weekly, 2),
                "estimated_stock_at_distributor": max(stock_at_dist, 0.0),
                "weeks_of_cover": round(weeks_of_cover, 1) if weeks_of_cover is not None else None,
                "reorder_signal": reorder_signal,
            })

        items.sort(key=lambda x: x.get("weeks_of_cover") or 999)
        top_performers = items[:20]
        bottom_performers = [i for i in items if i.get("reorder_signal")]

    except Exception:
        return {"data_unavailable": True, "reason": "Required fact tables not yet available", "items": [], "top_performers": [], "bottom_performers": []}

    return {
        "data_unavailable": False,
        "items": items,
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
    }


@router.get("/promotion-signals")
async def promotion_signals(
    db: AsyncSession = Depends(get_db),
    product_id: int | None = None,
) -> dict[str, Any]:
    """Pre-promotion baseline, uplift during, post-dip. Placeholder structure."""
    try:
        base_q = select(
            FactCustomerSales.product_id,
            DimProduct.sku.label("product_sku"),
            func.avg(FactCustomerSales.quantity_sold).label("avg_weekly_units"),
        ).outerjoin(
            DimProduct, FactCustomerSales.product_id == DimProduct.id
        ).where(FactCustomerSales.product_id.is_not(None))

        if product_id is not None:
            base_q = base_q.where(FactCustomerSales.product_id == int(product_id))

        base_q = base_q.group_by(FactCustomerSales.product_id, DimProduct.sku)
        rows = (await db.execute(base_q)).all()

        items: list[dict[str, Any]] = []
        for r in rows:
            baseline = float(r.avg_weekly_units or 0)
            items.append({
                "product_id": r.product_id,
                "product_sku": r.product_sku,
                "baseline_weekly_units": round(baseline, 2),
                "promotion_uplift_pct": None,
                "post_promotion_dip_pct": None,
                "signal": "insufficient_data",
            })

    except Exception:
        return {"data_unavailable": True, "reason": "Required fact tables not yet available", "items": []}

    return {"data_unavailable": False, "items": items}


@router.get("/pipeline")
async def pipeline_analytics(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Total units and value per stock journey state, velocity trend."""
    try:
        in_transit = await db.scalar(
            select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
                FactInboundShipment.status == "scheduled"
            )
        )
        in_transit_value = await db.scalar(
            select(func.coalesce(func.sum(FactInboundShipment.amount), 0)).where(
                FactInboundShipment.status == "scheduled"
            )
        )

        received = await db.scalar(
            select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
                FactInboundShipment.status == "received"
            )
        )
        dist_sold = await db.scalar(
            select(func.coalesce(func.sum(FactSalesSellout.units), 0))
        )
        cust_sold = await db.scalar(
            select(func.coalesce(func.sum(FactCustomerSales.quantity_sold), 0))
        )

        in_transit_units = float(in_transit or 0)
        at_distributor_units = float(received or 0) - float(dist_sold or 0)
        at_retailer_units = float(dist_sold or 0) - float(cust_sold or 0)
        sold_units = float(cust_sold or 0)

    except Exception:
        return {"data_unavailable": True, "reason": "Required fact tables not yet available", "states": []}

    return {
        "data_unavailable": False,
        "states": [
            {"state": "in_transit", "units": in_transit_units, "value": float(in_transit_value or 0)},
            {"state": "at_distributor", "units": max(at_distributor_units, 0.0), "value": None},
            {"state": "at_retailer", "units": max(at_retailer_units, 0.0), "value": None},
            {"state": "sold", "units": sold_units, "value": None},
        ],
        "total_pipeline_units": in_transit_units + max(at_distributor_units, 0.0) + max(at_retailer_units, 0.0),
    }
