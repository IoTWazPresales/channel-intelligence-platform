"""Coverage of each customer's reported products (N-0103).

One product sits in one bucket:

- watched: a listing is being checked on a site that has a reader, and the latest read did not fail
- failing: the listing is a dead link or the latest read failed, and nothing is being watched
- awaiting steward: an open link-queue row or a proposed feed row, and no listing yet
- not found: the queue says the product is not on the site, a steward rejected the only candidate, or a feed proposal was rejected
- not searched: the customer reported the product and none of the above has happened

``reported`` is the sum of those buckets. A sell-through read that fails is reported as
``data_unavailable`` and the other sources are still counted.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing, ListingObservation
from app.models.listing_link import QUEUE_NOT_ON_SITE, QUEUE_OPEN, QUEUE_REJECTED, ListingLinkQueue
from app.models.listing_site import ListingSite
from app.services.listing_capture.adapters import configured_adapter
from app.services.listing_capture.sites import site_config_from_row

logger = logging.getLogger(__name__)

_WATCHED = frozenset({"active", "out_of_stock"})
_BUCKETS = ("watched", "awaiting_steward", "failing", "not_found", "not_searched")


def customer_coverage(session: Session, tenant_id: str) -> dict[str, Any]:
    """Per-customer coverage for one tenant. Does not write."""
    try:
        with session.begin_nested():
            return _coverage(session, str(tenant_id))
    except Exception:
        logger.exception("listing coverage failed for tenant %s", tenant_id)
        return {"data_unavailable": True, "customers": []}


def _coverage(session: Session, tenant_id: str) -> dict[str, Any]:
    names = _customers(session, tenant_id)
    reported_products, sellthrough_down = _reported_products(session, tenant_id, names)
    states = _states(session, tenant_id, names, reported_products)
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {key: 0 for key in _BUCKETS})
    for (customer_id, _product_id), state in states.items():
        counts[customer_id][_bucket(state)] += 1
    _count_unlinked_seeds(session, tenant_id, names, counts)
    rows = []
    seen = set(counts) | {cid for cid, (_code, _name, reporting) in names.items() if reporting}
    for customer_id in seen:
        code, name, _reporting = _identity(names, customer_id)
        bucket = counts[customer_id]
        reported = sum(bucket.values())
        rows.append(
            {
                "customer_id": customer_id,
                "customer_code": code,
                "customer_name": name,
                "reported": reported,
                "watched": bucket["watched"],
                "awaiting_steward": bucket["awaiting_steward"],
                "failing": bucket["failing"],
                "not_found": bucket["not_found"],
                "not_searched": bucket["not_searched"],
            }
        )
    rows.sort(key=lambda row: (str(row["customer_name"]).casefold(), int(row["customer_id"])))
    return {"data_unavailable": sellthrough_down, "customers": rows}


def _identity(names: dict[int, tuple[str, str, bool]], customer_id: int) -> tuple[str, str, bool]:
    return names.get(customer_id, ("", "", False))


def _customers(session: Session, tenant_id: str) -> dict[int, tuple[str, str, bool]]:
    rows = session.execute(
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name, CustomerReportConfig.reports_expected)
        .outerjoin(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(DimCustomer.tenant_id == tenant_id)
    ).all()
    out: dict[int, tuple[str, str, bool]] = {}
    for customer_id, code, name, expected in rows:
        cid = int(customer_id)
        reporting = bool(expected)
        previous = out.get(cid)
        if previous is None or reporting:
            out[cid] = (str(code or ""), str(name or ""), reporting)
    return out


def _reported_products(
    session: Session,
    tenant_id: str,
    names: dict[int, tuple[str, str, bool]],
) -> tuple[set[tuple[int, int]], bool]:
    found: set[tuple[int, int]] = set()
    down = False
    try:
        with session.begin_nested():
            for customer_id, product_id in session.execute(
                select(FactCustomerSellthrough.customer_id, FactCustomerSellthrough.product_id)
                .where(FactCustomerSellthrough.tenant_id == tenant_id)
                .distinct()
            ).all():
                if customer_id is None or product_id is None:
                    continue
                cid = int(customer_id)
                if cid in names:
                    found.add((cid, int(product_id)))
    except Exception:
        logger.exception("listing coverage could not read sell-through")
        down = True
    for customer_id, product_id in session.execute(
        select(CstListingSeed.customer_id, CstListingSeed.product_id)
        .join(DimCustomer, DimCustomer.id == CstListingSeed.customer_id)
        .where(DimCustomer.tenant_id == tenant_id, CstListingSeed.product_id.is_not(None))
        .distinct()
    ).all():
        found.add((int(customer_id), int(product_id)))
    for customer_id, product_id in session.execute(
        select(CustomerListing.customer_id, CustomerListing.product_id)
        .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
        .where(DimCustomer.tenant_id == tenant_id, CustomerListing.product_id.is_not(None))
        .distinct()
    ).all():
        found.add((int(customer_id), int(product_id)))
    for customer_id, product_id in session.execute(
        select(ListingLinkQueue.customer_id, ListingLinkQueue.product_id).where(
            ListingLinkQueue.tenant_id == tenant_id,
            ListingLinkQueue.customer_id.is_not(None),
            ListingLinkQueue.product_id.is_not(None),
        )
    ).all():
        found.add((int(customer_id), int(product_id)))
    return found, down


class _State:
    def __init__(self) -> None:
        self.watched = False
        self.failing = False
        self.open_queue = False
        self.not_on_site = False
        self.rejected = False
        self.proposed = False


def _states(
    session: Session,
    tenant_id: str,
    names: dict[int, tuple[str, str, bool]],
    products: set[tuple[int, int]],
) -> dict[tuple[int, int], _State]:
    states = {key: _State() for key in products}
    readable = _readable_site_keys(session, tenant_id)
    listings = list(
        session.execute(
            select(
                CustomerListing.id,
                CustomerListing.customer_id,
                CustomerListing.product_id,
                CustomerListing.status,
                CustomerListing.marketplace,
            )
            .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
            .where(DimCustomer.tenant_id == tenant_id)
        ).all()
    )
    latest = _latest_parse(session, [int(row[0]) for row in listings if row[0] is not None])
    for listing_id, customer_id, product_id, status, marketplace in listings:
        if customer_id is None or int(customer_id) not in names:
            continue
        key = (int(customer_id), int(product_id)) if product_id is not None else None
        if key is None or key not in states:
            continue
        state = states[key]
        parse_status = latest.get(int(listing_id))
        listing_status = str(status or "")
        market = str(marketplace or "").strip().casefold()
        if listing_status in _WATCHED and parse_status != "parse_failed" and market in readable:
            state.watched = True
        elif listing_status == "dead_link" or parse_status == "parse_failed":
            state.failing = True
    for customer_id, product_id, status in session.execute(
        select(ListingLinkQueue.customer_id, ListingLinkQueue.product_id, ListingLinkQueue.status).where(
            ListingLinkQueue.tenant_id == tenant_id,
            ListingLinkQueue.customer_id.is_not(None),
            ListingLinkQueue.product_id.is_not(None),
        )
    ).all():
        key = (int(customer_id), int(product_id))
        state = states.get(key)
        if state is None:
            continue
        if status == QUEUE_OPEN:
            state.open_queue = True
        elif status == QUEUE_NOT_ON_SITE:
            state.not_on_site = True
        elif status == QUEUE_REJECTED:
            state.rejected = True
    for customer_id, product_id, status in session.execute(
        select(CstListingSeed.customer_id, CstListingSeed.product_id, CstListingSeed.status)
        .join(DimCustomer, DimCustomer.id == CstListingSeed.customer_id)
        .where(DimCustomer.tenant_id == tenant_id, CstListingSeed.product_id.is_not(None))
    ).all():
        key = (int(customer_id), int(product_id))
        state = states.get(key)
        if state is None:
            continue
        feed_status = str(status or "")
        if feed_status == "proposed":
            state.proposed = True
        elif feed_status == "rejected":
            state.rejected = True
    return states


def _count_unlinked_seeds(
    session: Session,
    tenant_id: str,
    names: dict[int, tuple[str, str, bool]],
    counts: dict[int, dict[str, int]],
) -> None:
    """A feed row with no product is still a coverage row. Proposed awaits a steward; rejected is not found."""
    for customer_id, status in session.execute(
        select(CstListingSeed.customer_id, CstListingSeed.status)
        .join(DimCustomer, DimCustomer.id == CstListingSeed.customer_id)
        .where(DimCustomer.tenant_id == tenant_id, CstListingSeed.product_id.is_(None))
    ).all():
        cid = int(customer_id)
        if cid not in names:
            continue
        feed_status = str(status or "")
        if feed_status == "proposed":
            counts[cid]["awaiting_steward"] += 1
        elif feed_status == "rejected":
            counts[cid]["not_found"] += 1


def _readable_site_keys(session: Session, tenant_id: str) -> set[str]:
    """Site keys whose reader is configured. A site with no reader is not watched."""
    keys: set[str] = set()
    rows = session.scalars(select(ListingSite).where(ListingSite.tenant_id == tenant_id)).all()
    for row in rows:
        if not isinstance(row, ListingSite):
            continue
        if configured_adapter(site_config_from_row(row)) is None:
            continue
        key = str(row.site_key or "").strip().casefold()
        if key:
            keys.add(key)
    return keys


def _latest_parse(session: Session, listing_ids: list[int]) -> dict[int, str]:
    if not listing_ids:
        return {}
    from sqlalchemy import func

    ranked = (
        select(
            ListingObservation.listing_id.label("listing_id"),
            ListingObservation.parse_status.label("parse_status"),
            func.row_number()
            .over(
                partition_by=ListingObservation.listing_id,
                order_by=(ListingObservation.fetched_at.desc(), ListingObservation.id.desc()),
            )
            .label("rn"),
        )
        .where(ListingObservation.listing_id.in_(listing_ids))
        .subquery()
    )
    rows = session.execute(select(ranked.c.listing_id, ranked.c.parse_status).where(ranked.c.rn == 1)).all()
    return {int(listing_id): str(parse_status or "") for listing_id, parse_status in rows}


def _bucket(state: _State) -> str:
    if state.watched:
        return "watched"
    if state.failing:
        return "failing"
    if state.open_queue or state.proposed:
        return "awaiting_steward"
    if state.not_on_site or state.rejected:
        return "not_found"
    return "not_searched"
