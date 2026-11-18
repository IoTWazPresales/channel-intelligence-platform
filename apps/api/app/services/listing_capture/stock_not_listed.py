"""In stock, not watched: a worklist of reported products with no watched listing (W1-B).

For each reporting customer, the products with stock on hand above zero on that customer's
latest stock report (the same product set discovery searches), less those that coverage
counts as watched. Each row says why it is not watched, using the coverage buckets:
awaiting steward, failing, not found, or not searched. Read-only; nothing is written.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.listing_capture.coverage import product_buckets

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 500
MAX_LIMIT = 2000

# What the account manager can do next, per coverage bucket. Words only; no action is taken.
NEXT_STEP = {
    "awaiting_steward": "A steward has a proposed link or queue row to decide.",
    "failing": "The listing is a dead link or its latest read failed; check the link.",
    "not_found": "Marked not on the site or delisted; confirm it is not sold there.",
    "not_searched": "No listing, proposal or search yet; add a listing or let discovery run.",
}


def stock_not_listed(
    session: Session,
    tenant_id: str,
    *,
    customer_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Worklist rows for one tenant (optionally one customer). Does not write."""
    cap = max(1, min(int(limit), MAX_LIMIT))
    try:
        with session.begin_nested():
            return _worklist(session, str(tenant_id), customer_id, cap)
    except Exception:
        logger.exception("stock-not-listed worklist failed for tenant %s", tenant_id)
        return {"data_unavailable": True, "rows": [], "total": 0, "truncated": False}


def _reporting_customers(
    session: Session, tenant_id: str, customer_id: int | None
) -> dict[int, tuple[str, str]]:
    stmt = (
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(DimCustomer.tenant_id == tenant_id, CustomerReportConfig.reports_expected.is_(True))
    )
    if customer_id is not None:
        stmt = stmt.where(DimCustomer.id == int(customer_id))
    return {
        int(cid): (str(code or ""), str(name or "")) for cid, code, name in session.execute(stmt)
    }


def _latest_stock(
    session: Session, tenant_id: str, customer_ids: list[int]
) -> dict[tuple[int, int], tuple[Any, float]]:
    """(customer, product) -> (latest stock date, units on hand that day, summed over sites)."""
    if not customer_ids:
        return {}
    latest = (
        select(
            FactCustomerSellthrough.customer_id.label("customer_id"),
            func.max(FactCustomerSellthrough.period_start_date).label("as_of"),
        )
        .where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.customer_id.in_(customer_ids),
            FactCustomerSellthrough.reported_soh.is_not(None),
        )
        .group_by(FactCustomerSellthrough.customer_id)
        .subquery()
    )
    rows = session.execute(
        select(
            FactCustomerSellthrough.customer_id,
            FactCustomerSellthrough.product_id,
            latest.c.as_of,
            func.sum(FactCustomerSellthrough.reported_soh),
        )
        .join(
            latest,
            (latest.c.customer_id == FactCustomerSellthrough.customer_id)
            & (latest.c.as_of == FactCustomerSellthrough.period_start_date),
        )
        .where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.product_id.is_not(None),
            FactCustomerSellthrough.reported_soh.is_not(None),
        )
        .group_by(
            FactCustomerSellthrough.customer_id, FactCustomerSellthrough.product_id, latest.c.as_of
        )
    ).all()
    out: dict[tuple[int, int], tuple[Any, float]] = {}
    for cid, pid, as_of, units in rows:
        if units is not None and float(units) > 0:
            out[(int(cid), int(pid))] = (as_of, float(units))
    return out


def _worklist(
    session: Session, tenant_id: str, customer_id: int | None, cap: int
) -> dict[str, Any]:
    customers = _reporting_customers(session, tenant_id, customer_id)
    stock = _latest_stock(session, tenant_id, sorted(customers))
    buckets = product_buckets(session, tenant_id, set(stock))
    open_keys = [key for key in stock if buckets.get(key, "not_searched") != "watched"]
    products: dict[int, tuple[str, str]] = {}
    pids = sorted({pid for _cid, pid in open_keys})
    for start in range(0, len(pids), 5000):
        for pid, sku, name in session.execute(
            select(DimProduct.id, DimProduct.sku, DimProduct.name).where(
                DimProduct.id.in_(pids[start : start + 5000])
            )
        ):
            products[int(pid)] = (str(sku or ""), str(name or ""))
    by_bucket: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    for cid, pid in open_keys:
        as_of, units = stock[(cid, pid)]
        bucket = buckets.get((cid, pid), "not_searched")
        by_bucket[bucket] += 1
        code, cname = customers.get(cid, ("", ""))
        sku, pname = products.get(pid, ("", ""))
        rows.append(
            {
                "customer_id": cid,
                "customer_code": code,
                "customer_name": cname,
                "product_id": pid,
                "sku": sku,
                "product_name": pname,
                "stock_on_hand": units,
                "stock_as_of": as_of.isoformat() if hasattr(as_of, "isoformat") else as_of,
                "coverage": bucket,
                "next_step": NEXT_STEP.get(bucket, ""),
            }
        )
    rows.sort(
        key=lambda r: (
            str(r["customer_name"]).casefold(),
            -float(r["stock_on_hand"]),
            r["product_id"],
        )
    )
    return {
        "data_unavailable": False,
        "total": len(rows),
        "truncated": len(rows) > cap,
        "by_coverage": dict(by_bucket),
        "watched_excluded": len(stock) - len(open_keys),
        "rows": rows[:cap],
    }
