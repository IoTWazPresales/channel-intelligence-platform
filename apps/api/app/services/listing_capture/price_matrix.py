"""Monitored-listings price matrix: scoped products × customers with latest shelf prices.

SRP means Suggested Retail Price. Warren's rule (26 Nov, verbatim): "use sell out price, fall back
to Line up price, fall back to website off promo price." It is resolved per customer and product:

1. ``sell_out_price``: the customer's latest sell-through ``unit_sell_price`` for the product
   (latest period with a positive price; the site row with most units when several report that
   period).
2. ``lineup_price``: the VAT-inclusive line-up price (``srp_inc_vat_local`` from the price chain,
   else ``msrp_local``) of the customer's latest line-up case whose period started on or before
   today. Only accepted cases (``ACCEPTED_OR_LATER_STATUSES``) supply an SRP: validated,
   pending_review, draft, proposed, rejected, cancelled and superseded never do.
3. ``website_off_promo_price``: the listing's struck-through regular price the site publishes
   (``parse_flags.rrp_listing_price`` on the latest good observation). No site that does not
   publish one gets a value here.

Every tier is stated on the shelf basis, VAT inclusive: a tier on a known ex-VAT basis is grossed up
with the tenant's own VAT rate, a tier whose basis is unknown or whose rate is unset is skipped
(same rule as ``planner_sellthrough.srp_from_price``). The highest price ever recorded is never used.
Each cell carries ``srp``, ``srp_source`` (one of the three codes), ``srp_period`` (ISO start date of
the sell-out or line-up period the figure came from, None for the website) and ``below_srp``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.commercial_tenant_profile import (
    DEFAULT_BELOW_SRP_TOLERANCE,
    below_srp_tolerance,
    configured_vat_rate_pct,
)
from app.services.commercial_planner.lineup_case_status import ACCEPTED_OR_LATER_STATUSES
from app.services.cpor.planner_sellthrough import srp_from_price
from app.services.cpor.promotion_type_vocab import CPOR_PROMOTION_TYPE_SET
from app.services.customer_reporting import reporting_customer_ids_select
from app.services.listing_capture.cpor_activation import _band_kind
from app.services.listing_capture.stock_scope import TIER_ACTIVE, TIER_HISTORICAL, product_tiers

_ACTIVE_LISTING_STATUSES = frozenset({"active", "out_of_stock"})
_EXCLUDED_CASE = frozenset({"cancelled", "rejected", "superseded", "draft", "proposed"})

# The three SRP sources, in the order Warren gave them. The first one with a value wins.
SRP_SOURCE_SELL_OUT = "sell_out_price"
SRP_SOURCE_LINEUP = "lineup_price"
SRP_SOURCE_WEBSITE = "website_off_promo_price"
SRP_SOURCE_ORDER: tuple[str, ...] = (SRP_SOURCE_SELL_OUT, SRP_SOURCE_LINEUP, SRP_SOURCE_WEBSITE)

# Reasons an SRP is missing. "Pending" is only used when no cell in the matrix has an SRP from any
# of the three sources; a single gap beside cells that do have one is ``no_srp_for_product``.
SRP_REASON_PENDING = "srp_source_pending"
SRP_REASON_NONE = "no_srp_for_product"
SRP_REASON_VARIES = "srp_varies_by_customer"

# The website tier reads the regular price the site publishes in the observation's parse flags.
_WEBSITE_REGULAR_PRICE_FLAG = "rrp_listing_price"
_WEBSITE_VAT_BASIS_FLAG = "vat_basis"

# A price counts as below SRP only when it is more than the tenant's tolerance (currency units) under
# it: ``below_srp_tolerance`` in the tenant profile, 1.0 when unset. The one place this rule lives:
# cells carry the resulting ``below_srp`` flag and the UI does no arithmetic.
BELOW_SRP_TOLERANCE = DEFAULT_BELOW_SRP_TOLERANCE

CellKey = tuple[int, int]  # (customer_id, product_id)
# One tier's answer for a cell: the SRP and the period it came from (None when the tier has none).
SrpFigure = tuple[float, date | None]


def is_below_srp(
    price: float | None,
    srp: float | None,
    *,
    in_stock: bool,
    tolerance: float = BELOW_SRP_TOLERANCE,
) -> bool:
    """In-stock prices only: an out-of-stock shelf price is not a live offer."""
    return bool(in_stock and price is not None and srp is not None and price < srp - tolerance)


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


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _sell_out_srp(
    session: Session,
    tenant_id: str,
    customer_ids: list[int],
    product_ids: list[int],
    vat_rate: float | None,
) -> dict[CellKey, SrpFigure]:
    """Tier 1: latest positive sell-through ``unit_sell_price`` per customer and product, incl. VAT.

    The figure carries the start of the sell-through period it was reported for.
    """
    st = FactCustomerSellthrough
    ranked = (
        select(
            st.customer_id,
            st.product_id,
            st.unit_sell_price,
            st.vat_basis,
            st.period_start_date,
            func.row_number()
            .over(
                partition_by=(st.customer_id, st.product_id),
                order_by=(st.period_start_date.desc(), st.units_sold.desc(), st.id.desc()),
            )
            .label("rn"),
        )
        .where(
            st.tenant_id == tenant_id,
            st.customer_id.in_(customer_ids),
            st.product_id.in_(product_ids),
            st.unit_sell_price > 0,
        )
        .subquery()
    )
    out: dict[CellKey, SrpFigure] = {}
    for row in session.execute(select(ranked).where(ranked.c.rn == 1)):
        srp, _reason = srp_from_price(_positive(row.unit_sell_price), row.vat_basis, vat_rate)
        if srp is not None:
            out[(int(row.customer_id), int(row.product_id))] = (srp, row.period_start_date)
    return out


def _lineup_srp(
    session: Session,
    tenant_id: str,
    customer_ids: list[int],
    product_ids: list[int],
    *,
    as_of: date,
) -> dict[CellKey, SrpFigure]:
    """Tier 2: the line-up SRP of the customer's latest live line-up case that started by ``as_of``.

    Warren: the line-up has the price excluding and including VAT. The shelf basis is the VAT-inclusive
    figure, read as stored: the price chain's explicit ``srp_inc_vat_local`` first, ``msrp_local``
    when the chain does not carry it. Only ACCEPTED cases supply one. Warren (26 Nov): "ONLY ACCEPTED ONES
    FFS". ASSUMPTION: accepted means ``accepted`` or any later ladder status (``ACCEPTED_OR_LATER_STATUSES``:
    po_pending ... work_closed), since a case a PO was raised against is an accepted case. Draft_imported,
    validated, pending_review, proposed, rejected, cancelled and superseded never supply one (an
    allow list, so any status added later is excluded until it is named there).
    The figure carries the case's period start.

    No currency check: listings, customers and sell-through rows carry no currency to compare the
    case's ``currency_code`` with, so a line-up in another currency is not detected here.
    """
    line, case = CommercialLineupLine, CommercialLineupCase
    explicit = line.pricing_chain_json["inputs"]["srp_inc_vat_local"].astext
    # Newest case first; the first line per cell that carries a USABLE figure wins (a newer line whose
    # chain value is "n/a" or 0 and whose msrp_local is 0 must not hide an older usable one).
    ranked = (
        select(
            line.customer_id,
            line.product_id,
            line.msrp_local,
            explicit.label("srp_inc_vat_local"),
            case.inferred_period_start.label("period_start"),
        )
        .join(case, case.id == line.case_id)
        .join(DimProduct, DimProduct.id == line.product_id)
        .where(
            DimProduct.tenant_id == tenant_id,
            line.customer_id.in_(customer_ids),
            line.product_id.in_(product_ids),
            or_(line.msrp_local > 0, explicit.is_not(None)),
            case.superseded_by_case_id.is_(None),
            func.lower(case.commercial_status).in_(sorted(ACCEPTED_OR_LATER_STATUSES)),
            case.inferred_period_start.is_not(None),
            case.inferred_period_start <= as_of,
        )
        .order_by(case.inferred_period_start.desc(), case.id.desc(), line.id.desc())
    )
    out: dict[CellKey, SrpFigure] = {}
    for row in session.execute(ranked):
        key = (int(row.customer_id), int(row.product_id))
        if key in out:
            continue
        value = _positive(row.srp_inc_vat_local) or _positive(row.msrp_local)
        if value is not None:
            out[key] = (value, row.period_start)
    return out


def _website_srp(
    listings: dict[CellKey, CustomerListing],
    latest: dict[int, ListingObservation],
    vat_rate: float | None,
) -> dict[CellKey, SrpFigure]:
    """Tier 3: the regular (struck-through) price the site publishes, incl. VAT (no period: it is current).

    Read from the latest good observation's parse flags. A site that publishes none (no flag) has
    no value here: the shelf price itself is never used, it may be a promotional price.
    """
    out: dict[CellKey, SrpFigure] = {}
    for key, listing in listings.items():
        obs = latest.get(int(listing.id))
        flags = obs.parse_flags if obs is not None and isinstance(obs.parse_flags, dict) else {}
        regular = _positive(flags.get(_WEBSITE_REGULAR_PRICE_FLAG))
        srp, _reason = srp_from_price(regular, flags.get(_WEBSITE_VAT_BASIS_FLAG), vat_rate)
        if srp is not None:
            out[key] = (srp, None)
    return out


def resolve_srp(tiers: dict[str, float | None]) -> tuple[float | None, str | None]:
    """The first source in ``SRP_SOURCE_ORDER`` that has a value: (srp, source code) or (None, None)."""
    for code in SRP_SOURCE_ORDER:
        value = tiers.get(code)
        if value is not None:
            return float(value), code
    return None, None


def _srp_by_cell(
    session: Session,
    tenant_id: str,
    *,
    listings: dict[CellKey, CustomerListing],
    latest: dict[int, ListingObservation],
    as_of: date,
) -> dict[CellKey, tuple[float, str, date | None]]:
    """SRP, its source and the period it came from per (customer, product) with a monitored listing.

    Gaps are absent. The period is None for a source that has none (the website's current price).
    """
    if not listings:
        return {}
    customer_ids = sorted({cid for cid, _ in listings})
    product_ids = sorted({pid for _, pid in listings})
    vat_rate = configured_vat_rate_pct(tenant_id)
    by_source: dict[str, dict[CellKey, SrpFigure]] = {
        SRP_SOURCE_SELL_OUT: _sell_out_srp(session, tenant_id, customer_ids, product_ids, vat_rate),
        SRP_SOURCE_LINEUP: _lineup_srp(session, tenant_id, customer_ids, product_ids, as_of=as_of),
        SRP_SOURCE_WEBSITE: _website_srp(listings, latest, vat_rate),
    }
    out: dict[CellKey, tuple[float, str, date | None]] = {}
    for key in listings:
        srp, source = resolve_srp(
            {code: (figures[key][0] if key in figures else None) for code, figures in by_source.items()}
        )
        if srp is not None and source is not None:
            out[key] = (srp, source, by_source[source][key][1])
    return out


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
            "summary": _summary(0, None),
            "srp_source_order": list(SRP_SOURCE_ORDER),
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
            "summary": _summary(0, None),
            "srp_source_order": list(SRP_SOURCE_ORDER),
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
    as_of = date.today()
    srp_by_cell = _srp_by_cell(
        session,
        tenant_id,
        listings={(cid, pid): listing for (pid, cid), listing in by_product_customer.items()},
        latest=latest,
        as_of=as_of,
    )
    any_srp = bool(srp_by_cell)
    tolerance = below_srp_tolerance(tenant_id)
    promo_pairs = {(int(l.customer_id), int(l.product_id)) for l in by_product_customer.values()}
    promos = _active_promos(session, as_of=as_of, pairs=promo_pairs)

    products = _product_labels(session, tenant_id, product_ids)
    customers = _customer_labels(session, customer_ids)
    cells: list[dict[str, Any]] = []
    below_srp_count = 0

    for product in products:
        pid = int(product["id"])
        found = [srp_by_cell[(cid, pid)][:2] for cid in customer_ids if (cid, pid) in srp_by_cell]
        product.update(_product_srp_fields(found, any_srp=any_srp))

    for pid in product_ids:
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
                        "srp": None,
                        "srp_source": None,
                        "srp_period": None,
                        "srp_reason": None,
                        "promo": None,
                    }
                )
                continue
            obs = latest.get(int(listing.id))
            price = float(obs.extracted_price) if obs and obs.extracted_price is not None else None
            in_stock = listing.status == "active" and price is not None
            found_srp = srp_by_cell.get((cid, pid))
            srp = found_srp[0] if found_srp else None
            below_srp = is_below_srp(price, srp, in_stock=in_stock, tolerance=tolerance)
            srp_period = found_srp[2] if found_srp else None
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
                    "srp": srp,
                    "srp_source": found_srp[1] if found_srp else None,
                    # ISO date of the start of the period the SRP came from; the UI formats it.
                    "srp_period": srp_period.isoformat() if srp_period is not None else None,
                    "srp_reason": None if found_srp else _missing_srp_reason(any_srp),
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
        "summary": _summary(len(product_ids), below_srp_count if any_srp else None),
        "srp_source_order": list(SRP_SOURCE_ORDER),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def _missing_srp_reason(any_srp: bool) -> str:
    """Pending only when no cell in the matrix has an SRP from any source."""
    return SRP_REASON_NONE if any_srp else SRP_REASON_PENDING


def _product_srp_fields(found: list[tuple[float, str]], *, any_srp: bool) -> dict[str, Any]:
    """Product-level SRP: the figure when every customer's SRP agrees, else no single figure.

    The per-customer SRP is on each cell; this keeps one SRP column for the row without picking
    one customer's figure over another's.
    """
    if not found:
        return {"srp": None, "srp_source": None, "srp_reason": _missing_srp_reason(any_srp)}
    values = {value for value, _ in found}
    if len(values) > 1:
        return {"srp": None, "srp_source": None, "srp_reason": SRP_REASON_VARIES}
    sources = {source for _, source in found}
    return {
        "srp": found[0][0],
        "srp_source": next(iter(sources)) if len(sources) == 1 else None,
        "srp_reason": None,
    }


def _summary(product_count: int, below_srp_count: int | None) -> dict[str, Any]:
    return {
        "product_count": product_count,
        # None, not 0, while no cell has an SRP: "0 below SRP" would claim a comparison.
        "below_srp_count": below_srp_count,
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