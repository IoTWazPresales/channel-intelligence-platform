"""Monitored-listings price matrix: scoped products × customers with latest shelf prices.

SRP means Suggested Retail Price. Its data source is not chosen yet: the read-only profile of live
data on 25 Nov found no line-up case covering today, no commercial plan and no historical line-up
rows (step log 02-step1). Until a source is chosen, every product and cell carries
``srp=None`` with ``srp_reason="srp_source_pending"``. No rule is invented, and the old "highest
MSRP ever" query is gone. ``_tenant_srp_by_product`` is the one seam to change when the source
is chosen.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.cpor.promotion_type_vocab import CPOR_PROMOTION_TYPE_SET
from app.services.customer_reporting import reporting_customer_ids_select
from app.services.listing_capture.cpor_activation import _band_kind
from app.services.listing_capture.stock_scope import TIER_ACTIVE, TIER_HISTORICAL, product_tiers

_ACTIVE_LISTING_STATUSES = frozenset({"active", "out_of_stock"})
_EXCLUDED_CASE = frozenset({"cancelled", "rejected", "superseded", "draft", "proposed"})

# None until the SRP data source is chosen (step 1, Phase B). Every row carries the reason.
SRP_SOURCE: str | None = None
SRP_REASON_PENDING = "srp_source_pending"

# A price counts as below SRP only when it is more than this many currency units under it. The one
# place this rule lives: cells carry the resulting ``below_srp`` flag and the UI does no arithmetic.
BELOW_SRP_TOLERANCE = 1.0


def is_below_srp(price: float | None, srp: float | None, *, in_stock: bool) -> bool:
    """In-stock prices only: an out-of-stock shelf price is not a live offer."""
    return bool(
        in_stock and price is not None and srp is not None and price < srp - BELOW_SRP_TOLERANCE
    )


def _latest_observations(session: Session, listing_ids: list[int]) -> dict[int, ListingObservation]:
    if not listing_ids:
        return {}
    sub = (
        select(
            ListingObservation.listing_id,
            func.max(ListingObservation.fetched_at).label("mx"),
        )
        .where(
            ListingObservation.listing_id.in_(listing_ids),
            ListingObservation.parse_status == "ok",
        )
        .group_by(ListingObservation.listing_id)
        .subquery()
    )
    rows = session.execute(
        select(ListingObservation).join(
            sub,
            (ListingObservation.listing_id == sub.c.listing_id)
            & (ListingObservation.fetched_at == sub.c.mx),
        )
    ).scalars().all()
    out: dict[int, ListingObservation] = {}
    for obs in rows:
        lid = int(obs.listing_id)
        if lid not in out or (obs.fetched_at and obs.fetched_at > out[lid].fetched_at):
            out[lid] = obs
    return out


def _tenant_srp_by_product(session: Session, tenant_id: str, product_ids: list[int]) -> dict[int, float]:
    """SRP per product from the chosen source. None is chosen yet, so nothing is returned.

    The earlier body took MAX(commercial_lineup_line.msrp_local) over every line-up ever. That rule
    was never requested and is removed. Callers report ``srp_reason`` for each missing value.
    """
    if SRP_SOURCE is None or not product_ids:
        return {}
    raise NotImplementedError(f"SRP source {SRP_SOURCE!r} is not implemented")


def _active_promos(
    session: Session, *, as_of: date, pairs: set[tuple[int, int]]
) -> dict[tuple[int, int], dict[str, Any]]:
    if not pairs:
        return {}
    customer_ids = {c for c, _ in pairs}
    product_ids = {p for _, p in pairs}
    rows = session.execute(
        select(CporCase, CporCaseLine)
        .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
        .where(
            CporCase.customer_id.in_(customer_ids),
            CporCaseLine.product_id.in_(product_ids),
            CporCase.window_start <= as_of,
            CporCase.window_end >= as_of,
            CporCase.superseded_by_case_id.is_(None),
            CporCase.promotion_type.in_(tuple(CPOR_PROMOTION_TYPE_SET)),
        )
    ).all()
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for case, line in rows:
        if (case.status or "").strip().lower() in _EXCLUDED_CASE:
            continue
        if _band_kind(case.promotion_type) != "promo":
            continue
        key = (int(case.customer_id), int(line.product_id))
        if key not in pairs:
            continue
        prev = out.get(key)
        if prev is None or int(case.id) > int(prev.get("case_id") or 0):
            out[key] = {
                "case_id": int(case.id),
                "name": (case.case_name or case.case_code or f"Case {case.id}").strip(),
                "window_start": case.window_start.isoformat() if case.window_start else None,
                "window_end": case.window_end.isoformat() if case.window_end else None,
                "promotion_type": case.promotion_type,
            }
    return out


def build_price_matrix(
    session: Session,
    *,
    tenant_id: str,
    customer_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Rows = scoped products with listings; columns = requested customers; cells = latest price."""
    if customer_ids is None:
        customer_ids = [
            int(x)
            for x in session.scalars(
                reporting_customer_ids_select().where(DimCustomer.tenant_id == tenant_id)
            ).all()
        ]
    customer_ids = sorted({int(c) for c in customer_ids if c is not None})
    if not customer_ids:
        return {
            "customers": [],
            "products": [],
            "cells": [],
            "summary": _summary(0, 0),
            "srp_source": SRP_SOURCE,
        }

    listings = list(
        session.scalars(
            select(CustomerListing).where(
                CustomerListing.customer_id.in_(customer_ids),
                CustomerListing.product_id.is_not(None),
                CustomerListing.status.in_(_ACTIVE_LISTING_STATUSES),
            )
        ).all()
    )
    if not listings:
        return {
            "customers": _customer_labels(session, customer_ids),
            "products": [],
            "cells": [],
            "summary": _summary(0, 0),
            "srp_source": SRP_SOURCE,
        }

    product_ids = sorted({int(l.product_id) for l in listings if l.product_id is not None})
    tiers = product_tiers(session, tenant_id, product_ids)
    if tiers is not None:
        product_ids = [pid for pid in product_ids if tiers.get(pid, TIER_ACTIVE) != TIER_HISTORICAL]
    listed_products = {int(l.product_id) for l in listings if l.product_id and int(l.product_id) in product_ids}
    product_ids = sorted(listed_products)

    by_product_customer: dict[tuple[int, int], CustomerListing] = {}
    for listing in listings:
        if listing.product_id is None:
            continue
        pid = int(listing.product_id)
        if pid not in product_ids:
            continue
        key = (pid, int(listing.customer_id))
        prev = by_product_customer.get(key)
        if prev is None or (listing.status == "active" and prev.status != "active"):
            by_product_customer[key] = listing

    listing_ids = [int(l.id) for l in by_product_customer.values()]
    latest = _latest_observations(session, listing_ids)
    srp_by_product = _tenant_srp_by_product(session, tenant_id, product_ids)
    as_of = date.today()
    promo_pairs = {(int(l.customer_id), int(l.product_id)) for l in by_product_customer.values()}
    promos = _active_promos(session, as_of=as_of, pairs=promo_pairs)

    products = _product_labels(session, tenant_id, product_ids)
    customers = _customer_labels(session, customer_ids)
    cells: list[dict[str, Any]] = []
    below_srp_count = 0

    for product in products:
        product.update(_srp_fields(srp_by_product.get(int(product["id"]))))

    for pid in product_ids:
        srp = srp_by_product.get(pid)
        srp_fields = _srp_fields(srp)
        for cid in customer_ids:
            listing = by_product_customer.get((pid, cid))
            if listing is None:
                cells.append(
                    {
                        "product_id": pid,
                        "customer_id": cid,
                        "price": None,
                        "observed_at": None,
                        "listing_id": None,
                        "listing_url": None,
                        "in_stock": False,
                        "below_srp": False,
                        **srp_fields,
                        "promo": None,
                    }
                )
                continue
            obs = latest.get(int(listing.id))
            price = float(obs.extracted_price) if obs and obs.extracted_price is not None else None
            in_stock = listing.status == "active" and price is not None
            below_srp = is_below_srp(price, srp, in_stock=in_stock)
            fetched = obs.fetched_at if obs is not None else None
            observed_at = fetched.isoformat() if fetched is not None else None
            cells.append(
                {
                    "product_id": pid,
                    "customer_id": cid,
                    "price": price,
                    "observed_at": observed_at,
                    "listing_id": int(listing.id),
                    "listing_url": listing.url,
                    "in_stock": in_stock,
                    "below_srp": below_srp,
                    **srp_fields,
                    "promo": promos.get((cid, pid)),
                }
            )
            # Listing capture has no price-freshness rule, so the age is returned per cell, not
            # used as a filter (A7).
            if below_srp:
                below_srp_count += 1

    return {
        "customers": customers,
        "products": products,
        "cells": cells,
        "summary": _summary(len(product_ids), below_srp_count),
        "srp_source": SRP_SOURCE,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def _srp_fields(srp: float | None) -> dict[str, Any]:
    if srp is not None:
        return {"srp": srp, "srp_source": SRP_SOURCE, "srp_reason": None}
    reason = SRP_REASON_PENDING if SRP_SOURCE is None else "no_srp_for_product"
    return {"srp": None, "srp_source": None, "srp_reason": reason}


def _summary(product_count: int, below_srp_count: int) -> dict[str, Any]:
    return {
        "product_count": product_count,
        # None, not 0, while there is no SRP source: "0 below SRP" would claim a comparison.
        "below_srp_count": below_srp_count if SRP_SOURCE is not None else None,
    }


def _customer_labels(session: Session, customer_ids: list[int]) -> list[dict[str, Any]]:
    rows = session.execute(select(DimCustomer).where(DimCustomer.id.in_(customer_ids))).scalars().all()
    by_id = {int(c.id): c for c in rows}
    return [
        {
            "id": cid,
            "name": (by_id[cid].name if cid in by_id else None) or (by_id[cid].code if cid in by_id else str(cid)),
            "code": by_id[cid].code if cid in by_id else None,
        }
        for cid in customer_ids
    ]


def _product_labels(session: Session, tenant_id: str, product_ids: list[int]) -> list[dict[str, Any]]:
    rows = session.execute(
        select(DimProduct).where(DimProduct.tenant_id == tenant_id, DimProduct.id.in_(product_ids))
    ).scalars().all()
    by_id = {int(p.id): p for p in rows}
    return [
        {
            "id": pid,
            "sales_model_name": by_id[pid].sales_model_name if pid in by_id else None,
            "sku": by_id[pid].sku if pid in by_id else None,
            "name": by_id[pid].name if pid in by_id else None,
        }
        for pid in product_ids
    ]