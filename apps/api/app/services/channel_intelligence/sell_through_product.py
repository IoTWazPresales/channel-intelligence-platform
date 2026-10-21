"""One product across customers, for the Sell-through detail panel (Warren 2026-10-19).

Opened from a row in "SKUs needing attention" or "Best sellers": what the product is (Product
Master fields and specs), and per customer: weekly sales over the last 26 weeks, latest stock with its
report date and the stores holding it, and the sell price the customer reported over time. Read-only.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.channel_intelligence.sell_through_overview import (
    LOOKBACK_WEEKS,
    OverviewFilters,
    _grain_of,
    _inc_vat,
    _period_days,
    load_stock_positions,
    product_label,
)
from app.services.commercial_planner.read_model import specs_json_flat_string_map


def product_detail(
    session: Session,
    *,
    tenant_id: str,
    product_id: int,
    as_of: date,
    vat: str,
    vat_rate: float,
    customer_ids: list[int] | None = None,
) -> dict[str, Any] | None:
    p = session.get(DimProduct, product_id)
    if p is None:
        return None
    s = FactCustomerSellthrough
    first = as_of - timedelta(days=LOOKBACK_WEEKS * 7 - 1)
    stmt = (
        select(
            s.customer_id,
            s.period_start_date,
            s.period_grain,
            s.period_type,
            s.vat_basis,
            func.sum(s.units_sold).label("units"),
            func.sum(s.units_sold * s.unit_sell_price).filter(s.unit_sell_price.is_not(None)).label("value"),
            func.sum(s.units_sold).filter(s.unit_sell_price.is_not(None)).label("priced_units"),
            func.avg(s.unit_sell_price).label("avg_price"),
        )
        .where(
            s.tenant_id == tenant_id,
            s.product_id == product_id,
            s.period_start_date >= first - timedelta(days=31),
            s.period_start_date <= as_of,
        )
        .group_by(s.customer_id, s.period_start_date, s.period_grain, s.period_type, s.vat_basis)
    )
    if customer_ids:
        stmt = stmt.where(s.customer_id.in_(customer_ids))

    want_inc = vat == "inc_vat"

    def conv(price: float, basis: str | None) -> float:
        row_inc = _inc_vat(basis)
        if row_inc and not want_inc:
            return price / (1 + vat_rate)
        if want_inc and not row_inc:
            return price * (1 + vat_rate)
        return price

    weekly: dict[int, list[float]] = defaultdict(lambda: [0.0] * LOOKBACK_WEEKS)
    prices: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in session.execute(stmt):
        cid = int(r.customer_id)
        grain = _grain_of(r.period_grain, r.period_type)
        days = _period_days(r.period_start_date, grain)
        units = float(r.units or 0)
        end = r.period_start_date + timedelta(days=days - 1)
        for i in range(LOOKBACK_WEEKS):
            a = first + timedelta(days=7 * i)
            b = a + timedelta(days=6)
            lo, hi = max(a, r.period_start_date), min(b, end)
            if hi >= lo:
                weekly[cid][i] += units * ((hi - lo).days + 1) / days
        if r.avg_price is not None:
            prices[cid].append({"period": r.period_start_date.isoformat(), "price": round(conv(float(r.avg_price), r.vat_basis), 2)})

    f = OverviewFilters(date_from=first, date_to=as_of, tenant_id=tenant_id, customer_ids=customer_ids or [], product_ids=[product_id])
    stock, stock_dates = load_stock_positions(session, f, as_of)
    cids = set(weekly) | {c for (c, _p) in stock}
    customers = {int(c.id): c for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(cids or {-1})))}

    rows = []
    for cid in cids:
        st = stock.get((cid, product_id))
        if st is None and cid in stock_dates:
            st = {"soh": 0.0, "on_order": 0.0, "in_transit": 0.0, "date": stock_dates[cid], "sites": []}
        pr = sorted(prices.get(cid, []), key=lambda x: x["period"])
        wk = weekly.get(cid, [0.0] * LOOKBACK_WEEKS)
        rows.append(
            {
                "customer_id": cid,
                "customer_name": customers[cid].name if cid in customers else f"Customer {cid}",
                "weekly_units": [round(u, 2) for u in wk],
                "units_26w": round(sum(wk), 2),
                "rate_4w": round(sum(wk[-4:]) / 4, 2),
                "stock_on_hand": round(st["soh"], 2) if st else None,
                "stock_date": st["date"].isoformat() if st else None,
                "stock_age_days": (as_of - st["date"]).days if st else None,
                "on_order": round(st["on_order"] + st["in_transit"], 2) if st else None,
                "stock_sites": [{"site": x["site"], "soh": round(x["soh"], 2)} for x in st["sites"]] if st else [],
                "price_history": pr[-26:],
                "latest_price": pr[-1]["price"] if pr else None,
            }
        )
    rows.sort(key=lambda r: (-r["units_26w"], r["customer_name"]))
    priced = [r for r in rows if r["latest_price"] is not None]
    lowest = min(priced, key=lambda r: r["latest_price"]) if priced else None
    return {
        "product": {
            "id": int(p.id),
            "label": product_label(p, int(p.id)),
            "sku": p.sku,
            "name": p.name,
            "sales_model_name": p.sales_model_name,
            "part_number": getattr(p, "part_number", None),
            "ean": p.ean,
            "upc": p.upc,
            "business_unit": p.business_unit,
            "category": p.category,
            "series": p.series_name,
            "product_line": p.product_line,
            "lifecycle": p.lifecycle_status,
            "launch_date": p.launch_date.isoformat() if p.launch_date else None,
            "retired_date": p.retired_date.isoformat() if p.retired_date else None,
            "price_band": p.price_band,
            "specs": specs_json_flat_string_map(p.specs_json, max_keys=60),
        },
        "as_of": as_of.isoformat(),
        "weeks_from": first.isoformat(),
        "vat": vat,
        "customers": rows,
        "lowest_price_customer": {"customer_name": lowest["customer_name"], "price": lowest["latest_price"]} if lowest else None,
    }
