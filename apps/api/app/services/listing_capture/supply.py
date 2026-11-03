"""Distributor sell-out that supplied a customer with a product.

Reads ``fact_sales_sellout`` rows whose resolved customer and product match.
No name matching. Nothing linked reads "not linked".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.facts import FactSalesSellout

NOT_LINKED = "not linked"


def sellout_supply(
    session: Session,
    *,
    customer_id: int | None,
    product_id: int | None,
    tenant_id: str,
) -> dict[str, Any]:
    if customer_id is None or product_id is None:
        return {"status": NOT_LINKED, "rows": []}
    period = func.date_trunc("month", FactSalesSellout.period_start)
    units = func.sum(FactSalesSellout.units)
    revenue = func.sum(FactSalesSellout.revenue)
    unit_price = func.avg(FactSalesSellout.unit_sellout_price_ex_tax_amount)
    stmt = (
        select(
            FactSalesSellout.distributor_id,
            DimDistributor.code,
            DimDistributor.name,
            period.label("period"),
            units.label("units"),
            revenue.label("revenue"),
            unit_price.label("unit_price"),
            func.max(FactSalesSellout.currency_code).label("currency_code"),
        )
        .join(DimDistributor, DimDistributor.id == FactSalesSellout.distributor_id)
        .where(
            FactSalesSellout.tenant_id == tenant_id,
            FactSalesSellout.customer_id == int(customer_id),
            FactSalesSellout.product_id == int(product_id),
            FactSalesSellout.distributor_id.is_not(None),
        )
        .group_by(FactSalesSellout.distributor_id, DimDistributor.code, DimDistributor.name, period)
        .order_by(period.desc(), DimDistributor.name)
    )
    rows = []
    for dist_id, code, name, per, unit_sum, rev, avg_price, currency in session.execute(stmt).all():
        units_n = float(unit_sum or 0)
        price = float(avg_price) if avg_price is not None else (float(rev) / units_n if units_n else None)
        rows.append(
            {
                "distributor_id": int(dist_id),
                "distributor_code": code,
                "distributor": name,
                "units": units_n,
                "price": price,
                "currency_code": currency,
                "period": per.date().isoformat() if hasattr(per, "date") else str(per)[:10],
            }
        )
    if not rows:
        return {"status": NOT_LINKED, "rows": []}
    return {"status": "linked", "rows": rows}
