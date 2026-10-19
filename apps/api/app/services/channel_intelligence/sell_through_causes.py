"""Existing intelligence brought to the Sell-through SKU list (Warren 2026-10-19).

Nothing here is new intelligence: each check reads data the platform already holds and says what it
found, with the evidence. A check with no data says "not checked" rather than implying the cause was
ruled out.

Outlook (feeds weeks of cover and the suggested order):
- promotion cases (``cpor_case`` / ``cpor_case_line``): planned units of current and upcoming
  promotions for the customer and product, spread over the line's window;
- inbound shipments shipped to the customer and not yet delivered (``fact_inbound_shipment``), at
  their expected delivery date.

Possible causes (shown on a flagged SKU):
- the customer's own reported sell price went up;
- the same product is cheaper at another customer (reported price or captured web listing);
- the customer's web listing is missing or shows unavailable (listing capture);
- stock is at the customer's other stores, or at a distributor that supplies the customer (DSI);
- a promotion ended around the time sales dropped; one is running or coming up;
- the same drop happened last year;
- a competitor product mapped to this one is cheaper (competitor prices, when loaded);
- the roadmap names a replacement model (when loaded);
- reported stock does not add up against last stock, sales and deliveries (the N-0110 stock gap).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment, FactInventoryDistributor

OUTLOOK_WEEKS = 26
PRICE_MOVE = 0.05  # a 5% difference counts as a price difference
_CLOSED_CASE_STATUSES = ("cancelled", "rejected")
_UNAVAILABLE_WORDS = ("out of stock", "unavailable", "sold out", "not available", "currently unavailable")


@dataclass
class Outlook:
    promos: list[dict[str, Any]] = field(default_factory=list)
    inbound: list[dict[str, Any]] = field(default_factory=list)


def _weeks_overlap(a0: date, a1: date, b0: date, b1: date) -> int:
    lo, hi = max(a0, b0), min(a1, b1)
    return (hi - lo).days + 1 if hi >= lo else 0


def load_outlook(
    session: Session, tenant_id: str, pairs: set[tuple[int, int]], as_of: date
) -> dict[tuple[int, int], Outlook]:
    """Promotions (ended in the last 12 weeks, running, or starting in the next 26) and inbound shipments per pair."""
    out: dict[tuple[int, int], Outlook] = defaultdict(Outlook)
    if not pairs:
        return out
    customers = sorted({c for c, _ in pairs})
    products = sorted({p for _, p in pairs})
    lo = as_of - timedelta(weeks=12)
    hi = as_of + timedelta(weeks=OUTLOOK_WEEKS)
    case_rows = session.execute(
        select(
            CporCase.customer_id,
            CporCaseLine.product_id,
            CporCase.case_code,
            CporCase.promotion_type,
            CporCase.status,
            CporCaseLine.window_start,
            CporCaseLine.window_end,
            CporCaseLine.estimate_qty,
            CporCaseLine.result_qty,
            CporCaseLine.srp,
        )
        .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
        .where(
            CporCase.tenant_id == tenant_id,
            CporCase.customer_id.in_(customers),
            CporCaseLine.product_id.in_(products),
            CporCase.status.not_in(_CLOSED_CASE_STATUSES),
            CporCase.superseded_by_case_id.is_(None),
            CporCaseLine.window_end >= lo,
            CporCaseLine.window_start <= hi,
        )
    )
    for r in case_rows:
        key = (int(r.customer_id), int(r.product_id))
        if key not in pairs:
            continue
        out[key].promos.append(
            {
                "case": r.case_code,
                "type": r.promotion_type,
                "status": r.status,
                "start": r.window_start,
                "end": r.window_end,
                "planned_units": float(r.estimate_qty or 0),
                "actual_units": float(r.result_qty) if r.result_qty is not None else None,
                "srp": float(r.srp) if r.srp is not None else None,
            }
        )
    sh = FactInboundShipment
    ship_rows = session.execute(
        select(
            sh.resolved_customer_id,
            sh.product_id,
            func.coalesce(sh.est_pod_date, sh.eta_date, sh.ship_confirm_date).label("eta"),
            func.sum(sh.quantity).label("qty"),
        )
        .where(
            sh.tenant_id == tenant_id,
            sh.resolved_customer_id.in_(customers),
            sh.product_id.in_(products),
            func.lower(sh.line_state) == "shipped",
            sh.pod_date.is_(None),
        )
        .group_by(sh.resolved_customer_id, sh.product_id, "eta")
    )
    for r in ship_rows:
        key = (int(r.resolved_customer_id), int(r.product_id))
        if key in pairs and float(r.qty or 0) > 0:
            out[key].inbound.append({"eta": r.eta, "units": float(r.qty)})
    return out


def forward_cover(
    *,
    stock: float,
    rate: float,
    anchor: date,
    outlook: Outlook | None,
    reported_incoming: float,
    target_weeks: float,
) -> dict[str, Any]:
    """Walk forward week by week from the customer's latest figures.

    Demand each week is the recent weekly rate plus planned promotion units that fall in that week
    (from promotions after ``anchor``); stock gains inbound shipments in the week they are due. The
    customer's own on-order / in-transit figure counts as arriving in week 1 where it exceeds the
    inbound shipments, so the two are not added twice.
    """
    promos = [p for p in (outlook.promos if outlook else []) if p["end"] > anchor and p["planned_units"] > 0]
    inbound = outlook.inbound if outlook else []
    inbound_total = sum(x["units"] for x in inbound)
    extra_incoming = max(0.0, reported_incoming - inbound_total)
    demand: list[float] = []
    arrivals: list[float] = []
    for w in range(OUTLOOK_WEEKS):
        a = anchor + timedelta(days=7 * w + 1)
        b = a + timedelta(days=6)
        promo_units = 0.0
        for p in promos:
            days = (p["end"] - p["start"]).days + 1
            promo_units += p["planned_units"] * _weeks_overlap(a, b, max(p["start"], anchor + timedelta(days=1)), p["end"]) / days
        demand.append(rate + promo_units)
        arrivals.append(extra_incoming if w == 0 else 0.0)
    for x in inbound:
        eta = x["eta"]
        w = 0 if eta is None or eta <= anchor else (eta - anchor - timedelta(days=1)).days // 7
        if w < OUTLOOK_WEEKS:
            arrivals[w] += x["units"]
    left = stock
    weeks: float | None = None
    for w in range(OUTLOOK_WEEKS):
        left += arrivals[w]
        if demand[w] <= 0:
            continue
        if left < demand[w]:
            weeks = w + max(0.0, left) / demand[w]
            break
        left -= demand[w]
    if weeks is None and sum(demand) > 0:
        weeks = float(OUTLOOK_WEEKS)
    full = int(math.floor(target_weeks))
    need = sum(demand[:full]) + (demand[full] * (target_weeks - full) if full < OUTLOOK_WEEKS else 0)
    suggested = math.ceil(need - stock - inbound_total - extra_incoming)
    return {
        "weeks": round(weeks, 1) if weeks is not None else None,
        "promo_units": round(sum(d - rate for d in demand), 2),
        "inbound_units": round(inbound_total, 2),
        "suggested": suggested if suggested > 0 else None,
        "promos_ahead": [p for p in promos if p["start"] > anchor],
        "promos_running": [p for p in promos if p["start"] <= anchor < p["end"]],
    }


# --------------------------------------------------------------------------- causes


def _latest_prices(session: Session, tenant_id: str, products: Iterable[int], since: date, vat: str, vat_rate: float) -> dict[tuple[int, int], list[tuple[date, float]]]:
    """Reported sell price per (customer, product) and period, in the requested VAT basis."""
    s = FactCustomerSellthrough
    out: dict[tuple[int, int], list[tuple[date, float]]] = defaultdict(list)
    rows = session.execute(
        select(s.customer_id, s.product_id, s.period_start_date, s.vat_basis, func.avg(s.unit_sell_price).label("p"))
        .where(s.tenant_id == tenant_id, s.product_id.in_(list(products)), s.period_start_date >= since, s.unit_sell_price.is_not(None))
        .group_by(s.customer_id, s.product_id, s.period_start_date, s.vat_basis)
    )
    want_inc = vat == "inc_vat"
    for r in rows:
        p = float(r.p)
        inc = str(r.vat_basis or "").lower().startswith("inc")
        if inc and not want_inc:
            p /= 1 + vat_rate
        elif want_inc and not inc:
            p *= 1 + vat_rate
        out[(int(r.customer_id), int(r.product_id))].append((r.period_start_date, p))
    for v in out.values():
        v.sort()
    return out


def _listings(session: Session, products: Iterable[int], vat: str, vat_rate: float) -> tuple[dict[tuple[int, int], dict[str, Any]], bool]:
    """Latest captured listing per (customer, product); listing prices are shelf prices (incl. VAT)."""
    try:
        from app.models.listing_capture import CustomerListing, ListingObservation
    except ImportError:  # pragma: no cover
        return {}, False
    ranked = (
        select(
            CustomerListing.customer_id,
            CustomerListing.product_id,
            CustomerListing.url,
            ListingObservation.fetched_at,
            ListingObservation.http_status,
            ListingObservation.extracted_price,
            ListingObservation.extracted_availability,
            ListingObservation.extracted_promo_badge,
            func.row_number()
            .over(partition_by=(CustomerListing.customer_id, CustomerListing.product_id), order_by=ListingObservation.fetched_at.desc())
            .label("rn"),
        )
        .join(ListingObservation, ListingObservation.listing_id == CustomerListing.id)
        .where(CustomerListing.product_id.in_(list(products)))
        .subquery()
    )
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for r in session.execute(select(ranked).where(ranked.c.rn == 1)):
        price = float(r.extracted_price) if r.extracted_price is not None else None
        if price is not None and vat != "inc_vat":
            price /= 1 + vat_rate
        out[(int(r.customer_id), int(r.product_id))] = {
            "url": r.url,
            "fetched_at": r.fetched_at.date().isoformat() if r.fetched_at else None,
            "http_status": r.http_status,
            "price": price,
            "availability": r.extracted_availability,
            "promo_badge": r.extracted_promo_badge,
        }
    any_listing = session.scalar(select(func.count()).select_from(CustomerListing)) or 0
    return out, bool(any_listing)


def _distributor_stock(session: Session, tenant_id: str, customers: Iterable[int], products: Iterable[int]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Latest DSI stock of each product at the customer's preferred distributor and at distributors that sell to it."""
    from app.models.fact_customer_velocity import FactCustomerVelocity

    customers = list(customers)
    products = list(products)
    links: dict[int, set[int]] = defaultdict(set)
    for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(customers or [-1]))):
        if c.preferred_distributor_id:
            links[int(c.id)].add(int(c.preferred_distributor_id))
    for r in session.execute(
        select(FactCustomerVelocity.customer_id, FactCustomerVelocity.distributor_id)
        .where(FactCustomerVelocity.customer_id.in_(customers or [-1]))
        .distinct()
    ):
        if r.customer_id is not None and r.distributor_id is not None:
            links[int(r.customer_id)].add(int(r.distributor_id))
    dists = sorted({d for ds in links.values() for d in ds})
    if not dists:
        return {}
    inv = FactInventoryDistributor
    latest = (
        select(inv.distributor_id, inv.product_id, func.max(inv.as_of_date).label("d"))
        .where(inv.tenant_id == tenant_id, inv.distributor_id.in_(dists), inv.product_id.in_(products or [-1]))
        .group_by(inv.distributor_id, inv.product_id)
        .subquery()
    )
    stock: dict[tuple[int, int], tuple[float, date]] = {}
    for r in session.execute(
        select(inv.distributor_id, inv.product_id, latest.c.d, func.sum(inv.on_hand_units).label("u"))
        .join(latest, and_(latest.c.distributor_id == inv.distributor_id, latest.c.product_id == inv.product_id, latest.c.d == inv.as_of_date))
        .where(inv.tenant_id == tenant_id)
        .group_by(inv.distributor_id, inv.product_id, latest.c.d)
    ):
        stock[(int(r.distributor_id), int(r.product_id))] = (float(r.u or 0), r.d)
    names = {int(d.id): d.name for d in session.scalars(select(DimDistributor).where(DimDistributor.id.in_(dists)))}
    out: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for c, ds in links.items():
        for p in products:
            for d in ds:
                u = stock.get((d, p))
                if u and u[0] > 0:
                    out[(c, p)].append({"distributor": names.get(d, f"Distributor {d}"), "units": u[0], "as_of": u[1].isoformat()})
    return out


def _competitor_prices(session: Session, products: Iterable[int]) -> tuple[dict[int, list[dict[str, Any]]], bool]:
    from app.models.dimensions import DimCompetitorBrand, DimCompetitorProduct
    from app.models.facts import FactCompetitorMapping, FactCompetitorPrice

    loaded = bool(session.scalar(select(func.count()).select_from(FactCompetitorPrice)))
    if not loaded:
        return {}, False
    latest = (
        select(FactCompetitorPrice.competitor_product_id, func.max(FactCompetitorPrice.observed_at).label("t"))
        .group_by(FactCompetitorPrice.competitor_product_id)
        .subquery()
    )
    rows = session.execute(
        select(
            FactCompetitorMapping.product_id,
            DimCompetitorProduct.sku,
            DimCompetitorProduct.name,
            DimCompetitorBrand.name.label("brand"),
            FactCompetitorPrice.price,
            FactCompetitorPrice.observed_at,
        )
        .join(DimCompetitorProduct, DimCompetitorProduct.id == FactCompetitorMapping.competitor_product_id)
        .join(DimCompetitorBrand, DimCompetitorBrand.id == DimCompetitorProduct.brand_id)
        .join(latest, latest.c.competitor_product_id == DimCompetitorProduct.id)
        .join(
            FactCompetitorPrice,
            and_(FactCompetitorPrice.competitor_product_id == DimCompetitorProduct.id, FactCompetitorPrice.observed_at == latest.c.t),
        )
        .where(FactCompetitorMapping.product_id.in_(list(products)), FactCompetitorMapping.approval_status == "approved")
    )
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        out[int(r.product_id)].append(
            {"label": f"{r.brand} {r.name or r.sku}".strip(), "price": float(r.price), "observed": str(r.observed_at)[:10]}
        )
    return out, True


def _replacements(session: Session, products: Iterable[int]) -> tuple[dict[int, str], bool]:
    from app.models.facts import FactProductRoadmap

    loaded = bool(session.scalar(select(func.count()).select_from(FactProductRoadmap)))
    if not loaded:
        return {}, False
    rows = session.execute(
        select(FactProductRoadmap.product_id, DimProduct.sku, DimProduct.sales_model_name)
        .join(DimProduct, DimProduct.id == FactProductRoadmap.replacement_candidate_id)
        .where(FactProductRoadmap.product_id.in_(list(products)))
    )
    return {int(r.product_id): (r.sales_model_name or r.sku) for r in rows}, True


def _stock_gaps(session: Session, tenant_id: str, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], dict[str, Any]]:
    """Latest compared stock-gap row (N-0110: expected vs reported on-hand) per pair, when over the tenant highlight."""
    from app.models.customer_stock_position import CustomerStockPosition as P
    from app.services.commercial_tenant_profile import stock_gap_highlight_units

    if not pairs:
        return {}
    limit = stock_gap_highlight_units(tenant_id)
    ranked = (
        select(
            P.customer_id, P.product_id, P.period_start_date, P.reported_on_hand, P.expected_on_hand, P.gap_units,
            func.row_number().over(partition_by=(P.customer_id, P.product_id), order_by=P.period_start_date.desc()).label("rn"),
        )
        .where(
            P.tenant_id == tenant_id,
            P.status == "compared",
            P.customer_id.in_(sorted({c for c, _ in pairs})),
            P.product_id.in_(sorted({p for _, p in pairs})),
        )
        .subquery()
    )
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for r in session.execute(select(ranked).where(ranked.c.rn == 1)):
        key = (int(r.customer_id), int(r.product_id))
        if key in pairs and r.gap_units is not None and abs(float(r.gap_units)) >= limit:
            out[key] = {
                "period": r.period_start_date.isoformat(),
                "reported": float(r.reported_on_hand or 0),
                "expected": float(r.expected_on_hand or 0),
                "gap": float(r.gap_units),
            }
    return out


def _pct(a: float, b: float) -> float:
    return (a - b) / b if b else 0.0


def attach_causes(
    session: Session,
    *,
    tenant_id: str,
    rows: list[dict[str, Any]],
    outlook: dict[tuple[int, int], Outlook],
    last_year_weeks: dict[tuple[int, int], list[float]],
    vat: str,
    vat_rate: float,
) -> None:
    """Add ``causes`` (what was found, with evidence) and ``not_checked`` (no data) to each row."""
    if not rows:
        return
    products = sorted({r["product_id"] for r in rows})
    customers = sorted({r["customer_id"] for r in rows})
    since = min(date.fromisoformat(r["judged_to"]) for r in rows) - timedelta(weeks=26)
    prices = _latest_prices(session, tenant_id, products, since, vat, vat_rate)
    listings, listings_loaded = _listings(session, products, vat, vat_rate)
    dist_stock = _distributor_stock(session, tenant_id, customers, products)
    competitors, competitors_loaded = _competitor_prices(session, products)
    replacements, roadmap_loaded = _replacements(session, products)
    gaps = _stock_gaps(session, tenant_id, {(r["customer_id"], r["product_id"]) for r in rows})
    cust_names = {int(c.id): c.name for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_({c for (c, _p) in prices} | set(customers))))}

    for r in rows:
        c, p = r["customer_id"], r["product_id"]
        anchor = date.fromisoformat(r["judged_to"])
        causes: list[dict[str, str]] = []
        not_checked: list[str] = []

        own = [x for x in prices.get((c, p), []) if x[0] <= anchor]
        own_now = own[-1][1] if own else None
        if own_now is not None:
            earlier = [x[1] for x in own if x[0] <= anchor - timedelta(weeks=8)]
            if earlier:
                before = earlier[-1]
                if _pct(own_now, before) >= PRICE_MOVE:
                    causes.append({"key": "price_up", "label": "Price went up", "detail": f"{before:,.0f} → {own_now:,.0f} ({_pct(own_now, before) * 100:+.0f}%)"})
        else:
            not_checked.append("own price (not in the files)")

        listing = listings.get((c, p))
        ref_price = own_now if own_now is not None else (listing["price"] if listing and listing.get("price") else None)
        if ref_price:
            cheaper = []
            for (oc, op), hist in prices.items():
                if op != p or oc == c or not hist:
                    continue
                if _pct(hist[-1][1], ref_price) <= -PRICE_MOVE:
                    cheaper.append((hist[-1][1], cust_names.get(oc, f"Customer {oc}"), "reported"))
            for (oc, op), l in listings.items():
                if op == p and oc != c and l.get("price") and _pct(l["price"], ref_price) <= -PRICE_MOVE:
                    cheaper.append((l["price"], cust_names.get(oc, f"Customer {oc}"), "web listing"))
            if cheaper:
                best = min(cheaper)
                causes.append({"key": "cheaper_elsewhere", "label": "Cheaper elsewhere", "detail": f"{best[1]} {best[0]:,.0f} ({best[2]}) vs {ref_price:,.0f} ({_pct(best[0], ref_price) * 100:+.0f}%)"})

        if listing:
            status = listing.get("http_status")
            avail = str(listing.get("availability") or "").lower()
            if status and int(status) >= 400:
                causes.append({"key": "no_page", "label": "Web page missing", "detail": f"HTTP {status} on {listing['fetched_at']}"})
            elif any(w in avail for w in _UNAVAILABLE_WORDS):
                causes.append({"key": "listing_unavailable", "label": "Listed as unavailable", "detail": f"'{listing['availability']}' on {listing['fetched_at']}"})
        elif listings_loaded:
            not_checked.append("web listing (none registered for this customer)")
        else:
            not_checked.append("web listing (no listings captured)")

        sites = r.get("stock_sites") or []
        if r["reason"] in ("out_of_stock", "needs_replen", "dropped") and len(sites) > 0:
            causes.append({"key": "stock_at_stores", "label": "Stock at other stores", "detail": ", ".join(f"{s['site']} {s['soh']:,.0f}" for s in sites[:4])})
        dstock = dist_stock.get((c, p))
        if r["reason"] in ("out_of_stock", "needs_replen") and dstock:
            causes.append({"key": "distributor_stock", "label": "Distributor has stock", "detail": "; ".join(f"{d['distributor']} {d['units']:,.0f} ({d['as_of']})" for d in dstock[:3])})

        ol = outlook.get((c, p))
        for pr in (ol.promos if ol else []):
            if pr["end"] <= anchor and pr["end"] >= anchor - timedelta(weeks=12) and r["reason"] in ("dropped", "stopped", "aged"):
                causes.append({"key": "promo_ended", "label": "Promotion ended", "detail": f"{pr['type']} {pr['case']} ended {pr['end'].isoformat()}"})
            elif pr["start"] <= anchor < pr["end"]:
                causes.append({"key": "promo_running", "label": "Promotion running", "detail": f"{pr['type']} until {pr['end'].isoformat()}, {pr['planned_units']:,.0f} units planned"})
            elif pr["start"] > anchor:
                causes.append({"key": "promo_ahead", "label": "Promotion coming", "detail": f"{pr['type']} from {pr['start'].isoformat()}, {pr['planned_units']:,.0f} units planned"})
        for x in (ol.inbound if ol else []):
            causes.append({"key": "inbound", "label": "On its way", "detail": f"{x['units']:,.0f} shipped, due {x['eta'].isoformat() if x['eta'] else 'date unknown'}"})

        gap = gaps.get((c, p))
        if gap:
            causes.append({"key": "stock_gap", "label": "Stock does not add up", "detail": f"{gap['period']}: reported {gap['reported']:,.0f}, expected {gap['expected']:,.0f} from last stock, sales and deliveries ({gap['gap']:+,.0f})"})

        ly = last_year_weeks.get((c, p))
        if r["reason"] == "dropped" and ly and sum(ly[-12:-4]) > 0:
            ly_before = sum(ly[-12:-4]) / 8
            ly_now = sum(ly[-4:]) / 4
            if ly_now <= ly_before * 0.5:
                causes.append({"key": "seasonal", "label": "Same drop last year", "detail": f"{ly_before:,.1f} → {ly_now:,.1f} a week in the same weeks last year"})

        if competitors_loaded:
            ref = own_now or (listing or {}).get("price")
            lower = [x for x in competitors.get(p, []) if ref and _pct(x["price"], ref) <= -PRICE_MOVE]
            if lower:
                x = min(lower, key=lambda y: y["price"])
                causes.append({"key": "competitor_cheaper", "label": "Competitor cheaper", "detail": f"{x['label']} {x['price']:,.0f} ({x['observed']})"})
        else:
            not_checked.append("competitor prices (none loaded)")
        if roadmap_loaded:
            if p in replacements:
                causes.append({"key": "replaced", "label": "Replacement model", "detail": f"Roadmap names {replacements[p]}"})
        else:
            not_checked.append("replacement model (no roadmap loaded)")
        not_checked.append("search ranking (no data source)")

        r["causes"] = causes
        r["not_checked"] = not_checked
