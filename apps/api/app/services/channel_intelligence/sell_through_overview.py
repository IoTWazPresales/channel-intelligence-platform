"""Sell-through overview: what retailers sold, what they hold, which reports are missing and which
SKUs need attention, for one window and set of filters (Warren 2026-10-19).

Compute-on-read over ``fact_customer_sellthrough``; nothing is written. Periods follow the tenant's
business calendar (``app.services.business_calendar``).

Rules worth knowing:

- A row covers its period (a day, a week or a month). When a window or a chart bucket covers part of
  a row's period, the row counts in proportion to the days covered, so a monthly figure is spread
  evenly over its days when shown by week or day. Nothing finer than the file is invented.
- Sales value is units x the reported sell price, converted to excluding or including VAT from the
  basis the customer reports in. Where a row has no price, the latest captured listing price for
  that customer and product is used and the value is marked as estimated.
- Stock on hand is what the customer reported on its latest stock date; a product missing from that
  report holds 0. Customers that never report stock have no stock figure (not 0).
- SKU problems are judged up to each customer's own last reported day, so a report that has not
  arrived yet does not read as a sales drop.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.customer_report_config import (
    DEFAULT_REPLEN_MIN_WEEKS_OF_COVER,
    DEFAULT_REPLEN_TARGET_WEEKS_OF_COVER,
    CustomerReportConfig,
)
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.business_calendar import Bucket, BusinessCalendar

GRAINS = ("day", "week", "month", "quarter")
COMPARES = ("none", "prior_period", "prior_year")

# SKU problem rules (Warren 2026-10-19: "worst sellers" means good sellers that dropped, stock that is
# not moving, and SKUs with no sales for a while — not the long tail of zero lines).
LOOKBACK_WEEKS = 26
RECENT_WEEKS = 4
STREAK_WEEKS = 8
STREAK_MIN_SELLING_WEEKS = 6
DROP_MIN_UNITS_PER_WEEK = 1.0
DROP_RATIO = 0.5
NO_SALES_WEEKS = 8
PROBLEM_ROW_LIMIT = 300
STOCK_STALE_DAYS = 35
TOP_N = 10

REASONS = ("out_of_stock", "needs_replen", "dropped", "aged", "stopped")
REASON_LABELS = {
    "out_of_stock": "Out of stock, was selling",
    "needs_replen": "Needs replenishing",
    "dropped": "Sales dropped",
    "aged": "Aged stock",
    "stopped": "No recent sales",
}
_ENDED_WORDS = ("eol", "end of life", "retire", "obsolete", "discontinu", "phase out", "phased out", "sunset")


@dataclass
class OverviewFilters:
    date_from: date
    date_to: date
    grain: str = "week"
    compare: str = "prior_year"
    vat: str = "ex_vat"
    customer_ids: list[int] = field(default_factory=list)
    business_units: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    series: list[str] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    tenant_id: str = "default"


@dataclass
class Obs:
    customer_id: int
    product_id: int
    start: date
    days: int
    units: float
    value: float | None  # in the requested VAT basis; None when no price is known
    value_estimated: bool
    soh: float | None
    on_order: float
    in_transit: float

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.days - 1)

    def share(self, a: date, b: date) -> float:
        """Fraction of this row's period inside [a, b]."""
        lo = max(a, self.start)
        hi = min(b, self.end)
        if hi < lo:
            return 0.0
        return ((hi - lo).days + 1) / self.days


# --------------------------------------------------------------------------- loading


def _grain_of(period_grain: str | None, period_type: str | None) -> str:
    g = (period_grain or "").strip().lower()
    if g in ("day", "week", "month"):
        return g
    pt = (period_type or "").strip().lower()
    if pt.startswith("month"):
        return "month"
    if pt.startswith("da"):
        return "day"
    return "week"


def _period_days(start: date, grain: str) -> int:
    if grain == "day":
        return 1
    if grain == "week":
        return 7
    nxt_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
    try:
        nxt = nxt_month.replace(day=start.day)
    except ValueError:
        nxt = nxt_month + timedelta(days=start.day - 1)
    return max(1, (nxt - start).days)


def _inc_vat(basis: str | None) -> bool:
    return str(basis or "").strip().lower().startswith("inc")


def _product_filter(f: OverviewFilters) -> list[Any]:
    conds: list[Any] = []
    if f.product_ids:
        conds.append(DimProduct.id.in_(f.product_ids))
    if f.business_units:
        conds.append(DimProduct.business_unit.in_(f.business_units))
    if f.categories:
        conds.append(DimProduct.category.in_(f.categories))
    if f.series:
        conds.append(DimProduct.series_name.in_(f.series))
    return conds


def _listing_prices(session: Session, pairs: set[tuple[int, int]]) -> dict[tuple[int, int], float]:
    """Latest captured listing price per (customer, product). Listing prices are shelf prices (incl. VAT)."""
    if not pairs:
        return {}
    try:
        from app.models.listing_capture import CustomerListing, ListingObservation
    except ImportError:  # pragma: no cover
        return {}
    customers = sorted({c for c, _ in pairs})
    latest = (
        select(
            CustomerListing.customer_id,
            CustomerListing.product_id,
            ListingObservation.extracted_price,
            func.row_number()
            .over(
                partition_by=(CustomerListing.customer_id, CustomerListing.product_id),
                order_by=ListingObservation.fetched_at.desc(),
            )
            .label("rn"),
        )
        .join(ListingObservation, ListingObservation.listing_id == CustomerListing.id)
        .where(
            CustomerListing.customer_id.in_(customers),
            CustomerListing.product_id.is_not(None),
            ListingObservation.extracted_price.is_not(None),
        )
        .subquery()
    )
    out: dict[tuple[int, int], float] = {}
    for row in session.execute(select(latest.c.customer_id, latest.c.product_id, latest.c.extracted_price).where(latest.c.rn == 1)):
        key = (int(row.customer_id), int(row.product_id))
        if key in pairs and row.extracted_price is not None:
            out[key] = float(row.extracted_price)
    return out


def load_observations(
    session: Session,
    f: OverviewFilters,
    load_from: date,
    load_to: date,
    *,
    vat_rate: float,
) -> list[Obs]:
    s = FactCustomerSellthrough
    priced = s.unit_sell_price.is_not(None)
    stmt = (
        select(
            s.customer_id,
            s.product_id,
            s.period_start_date,
            s.period_grain,
            s.period_type,
            s.vat_basis,
            func.sum(s.units_sold).label("units"),
            func.sum(s.units_sold * s.unit_sell_price).filter(priced).label("value"),
            func.sum(s.units_sold).filter(priced).label("priced_units"),
            func.sum(s.reported_soh).filter(s.reported_soh.is_not(None)).label("soh"),
            func.count(s.reported_soh).label("soh_rows"),
            func.sum(func.coalesce(s.on_order_units, 0)).label("on_order"),
            func.sum(func.coalesce(s.in_transit_units, 0)).label("in_transit"),
        )
        .where(
            s.tenant_id == f.tenant_id,
            s.period_start_date >= load_from - timedelta(days=31),
            s.period_start_date <= load_to,
        )
        .group_by(s.customer_id, s.product_id, s.period_start_date, s.period_grain, s.period_type, s.vat_basis)
    )
    if f.customer_ids:
        stmt = stmt.where(s.customer_id.in_(f.customer_ids))
    pconds = _product_filter(f)
    if pconds:
        stmt = stmt.join(DimProduct, DimProduct.id == s.product_id).where(and_(*pconds))

    raw = list(session.execute(stmt))
    unpriced_pairs = {
        (int(r.customer_id), int(r.product_id))
        for r in raw
        if float(r.units or 0) != 0 and float(r.priced_units or 0) < float(r.units or 0)
    }
    listing = _listing_prices(session, unpriced_pairs)

    want_inc = f.vat == "inc_vat"
    merged: dict[tuple[int, int, date, str], Obs] = {}
    for r in raw:
        grain = _grain_of(r.period_grain, r.period_type)
        units = float(r.units or 0)
        priced_units = float(r.priced_units or 0)
        value: float | None = None
        estimated = False
        if r.value is not None:
            v = float(r.value)
            row_inc = _inc_vat(r.vat_basis)
            if row_inc and not want_inc:
                v /= 1 + vat_rate
            elif want_inc and not row_inc:
                v *= 1 + vat_rate
            value = v
        missing_units = units - priced_units
        if abs(missing_units) > 1e-9:
            lp = listing.get((int(r.customer_id), int(r.product_id)))
            if lp is not None:
                extra = missing_units * (lp if want_inc else lp / (1 + vat_rate))
                value = (value or 0.0) + extra
                estimated = True
        key = (int(r.customer_id), int(r.product_id), r.period_start_date, grain)
        soh = float(r.soh) if int(r.soh_rows or 0) > 0 and r.soh is not None else None
        o = merged.get(key)
        if o is None:
            merged[key] = Obs(
                customer_id=key[0],
                product_id=key[1],
                start=r.period_start_date,
                days=_period_days(r.period_start_date, grain),
                units=units,
                value=value,
                value_estimated=estimated,
                soh=soh,
                on_order=float(r.on_order or 0),
                in_transit=float(r.in_transit or 0),
            )
        else:  # same period reported under two VAT bases
            o.units += units
            if value is not None:
                o.value = (o.value or 0.0) + value
            o.value_estimated = o.value_estimated or estimated
            if soh is not None:
                o.soh = (o.soh or 0.0) + soh
            o.on_order += float(r.on_order or 0)
            o.in_transit += float(r.in_transit or 0)
    return list(merged.values())


# --------------------------------------------------------------------------- helpers


def _sum_window(obs: Iterable[Obs], a: date, b: date) -> tuple[float, float, float]:
    """(units, value, estimated value) inside [a, b]."""
    units = value = est = 0.0
    for o in obs:
        sh = o.share(a, b)
        if sh <= 0:
            continue
        units += o.units * sh
        if o.value is not None:
            value += o.value * sh
            if o.value_estimated:
                est += o.value * sh
    return units, value, est


def _pct(cur: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return (cur - prev) / abs(prev)


def compare_window(cal: BusinessCalendar, f: OverviewFilters) -> tuple[date, date] | None:
    if f.compare == "prior_year":
        if f.grain in ("day", "week") and cal.type == "gregorian":
            # By day or week, compare the same weekdays: 52 weeks back.
            return f.date_from - timedelta(weeks=52), f.date_to - timedelta(weeks=52)
        return cal.same_day_last_year(f.date_from), cal.same_day_last_year(f.date_to)
    if f.compare == "prior_period":
        span = (f.date_to - f.date_from).days + 1
        return f.date_from - timedelta(days=span), f.date_from - timedelta(days=1)
    return None


def _bucket_index(buckets: list[Bucket]) -> list[date]:
    return [b.start for b in buckets]


def _spread(obs: Iterable[Obs], buckets: list[Bucket], starts: list[date], sink) -> None:
    """Call ``sink(obs, bucket_index, share)`` for each bucket a row overlaps."""
    if not buckets:
        return
    first, last = buckets[0].start, buckets[-1].end
    for o in obs:
        if o.end < first or o.start > last:
            continue
        i = max(0, bisect.bisect_right(starts, o.start) - 1)
        while i < len(buckets) and buckets[i].start <= o.end:
            sh = o.share(buckets[i].start, buckets[i].end)
            if sh > 0:
                sink(o, i, sh)
            i += 1


def _covered_intervals(obs: Iterable[Obs]) -> dict[int, list[tuple[date, date]]]:
    per: dict[int, list[tuple[date, date]]] = defaultdict(list)
    for o in obs:
        per[o.customer_id].append((o.start, o.end))
    merged: dict[int, list[tuple[date, date]]] = {}
    for cid, spans in per.items():
        spans.sort()
        out: list[tuple[date, date]] = []
        for a, b in spans:
            if out and a <= out[-1][1] + timedelta(days=1):
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        merged[cid] = out
    return merged


def _covered_days(spans: list[tuple[date, date]], a: date, b: date) -> int:
    n = 0
    for s, e in spans:
        lo, hi = max(a, s), min(b, e)
        if hi >= lo:
            n += (hi - lo).days + 1
    return n


def _is_ended(p: DimProduct | None, on: date) -> bool:
    if p is None:
        return False
    if p.retired_date is not None and p.retired_date <= on:
        return True
    status = str(p.lifecycle_status or "").strip().lower()
    return any(w in status for w in _ENDED_WORDS)


def product_label(p: DimProduct | None, product_id: int) -> str:
    if p is None:
        return f"Product {product_id}"
    name = p.sales_model_name or p.name
    return f"{name} ({p.sku})" if name and p.sku and name != p.sku else (name or p.sku or f"Product {product_id}")


# --------------------------------------------------------------------------- overview


def build_overview(session: Session, f: OverviewFilters, cal: BusinessCalendar, *, today: date, vat_rate: float) -> dict[str, Any]:
    if f.grain not in GRAINS:
        raise ValueError(f"grain must be one of {list(GRAINS)}")
    if f.compare not in COMPARES:
        raise ValueError(f"compare must be one of {list(COMPARES)}")
    if f.date_to < f.date_from:
        raise ValueError("date_to is before date_from")

    cmp = compare_window(cal, f)
    quarter_now = cal.bucket(f.date_to, "quarter")
    quarters = []
    q = quarter_now
    for _ in range(5):
        quarters.insert(0, q)
        q = cal.bucket(q.start - timedelta(days=1), "quarter")
    quarters_ly_from = cal.same_day_last_year(quarters[0].start)
    problem_from = f.date_to - timedelta(weeks=LOOKBACK_WEEKS + 1)
    load_from = min(d for d in (f.date_from, cmp[0] if cmp else f.date_from, quarters_ly_from, problem_from))
    obs = load_observations(session, f, load_from, f.date_to, vat_rate=vat_rate)

    # Customers in view: the reporting customers plus any customer with figures.
    cfg_rows = list(
        session.execute(
            select(CustomerReportConfig, DimCustomer)
            .join(DimCustomer, DimCustomer.id == CustomerReportConfig.customer_id)
            .where(or_(CustomerReportConfig.reports_expected.is_(True), DimCustomer.is_key_account.is_(True)))
        )
    )
    cfg_by_customer: dict[int, CustomerReportConfig] = {}
    for cfg, _cust in cfg_rows:
        cfg_by_customer[int(cfg.customer_id)] = cfg
    customer_ids = {int(c) for c in cfg_by_customer} | {o.customer_id for o in obs}
    if f.customer_ids:
        customer_ids &= set(f.customer_ids)
    extra_cfg = set(customer_ids) - set(cfg_by_customer)
    if extra_cfg:
        for cfg in session.scalars(select(CustomerReportConfig).where(CustomerReportConfig.customer_id.in_(extra_cfg))):
            cfg_by_customer[int(cfg.customer_id)] = cfg
    customers = {
        int(c.id): c for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(customer_ids or {-1})))
    }
    product_ids = {o.product_id for o in obs}
    products = {
        int(p.id): p for p in session.scalars(select(DimProduct).where(DimProduct.id.in_(product_ids or {-1})))
    }

    in_window = [o for o in obs if o.share(f.date_from, f.date_to) > 0]
    in_cmp = [o for o in obs if cmp and o.share(cmp[0], cmp[1]) > 0]

    # ---- headline numbers
    units, value, est_value = _sum_window(in_window, f.date_from, f.date_to)
    c_units, c_value, _ = _sum_window(in_cmp, cmp[0], cmp[1]) if cmp else (0.0, 0.0, 0.0)
    units_no_value = sum(o.units * o.share(f.date_from, f.date_to) for o in in_window if o.value is None)

    stock = _stock_positions(obs, f.date_to)
    soh_total = sum(v["soh"] for v in stock.values())
    stock_customers = {c for (c, _p) in stock}
    rate4_by_pair: dict[tuple[int, int], float] = defaultdict(float)
    for o in obs:
        sh = o.share(f.date_to - timedelta(days=RECENT_WEEKS * 7 - 1), f.date_to)
        if sh > 0:
            rate4_by_pair[(o.customer_id, o.product_id)] += o.units * sh / RECENT_WEEKS
    rate4_stocked = sum(r for (c, _p), r in rate4_by_pair.items() if c in stock_customers)

    # ---- trend
    buckets = cal.buckets(f.date_from, f.date_to, f.grain)
    starts = _bucket_index(buckets)
    trend = [
        {**b.as_dict(), "units": 0.0, "value": 0.0, "by_customer": defaultdict(float)} for b in buckets
    ]

    def _trend_sink(o: Obs, i: int, sh: float) -> None:
        trend[i]["units"] += o.units * sh
        if o.value is not None:
            trend[i]["value"] += o.value * sh
        trend[i]["by_customer"][o.customer_id] += o.units * sh

    _spread(in_window, buckets, starts, _trend_sink)
    if cmp:
        c_buckets = cal.buckets(cmp[0], cmp[1], f.grain)
        c_series = [{"units": 0.0, "value": 0.0, "label": b.label, "start": b.start.isoformat()} for b in c_buckets]

        def _cmp_sink(o: Obs, i: int, sh: float) -> None:
            c_series[i]["units"] += o.units * sh
            if o.value is not None:
                c_series[i]["value"] += o.value * sh

        _spread(in_cmp, c_buckets, _bucket_index(c_buckets), _cmp_sink)
        for i, t in enumerate(trend):
            if i < len(c_series):
                t["compare_units"] = round(c_series[i]["units"], 2)
                t["compare_value"] = round(c_series[i]["value"], 2)
                t["compare_label"] = c_series[i]["label"]
    for t in trend:
        t["units"] = round(t["units"], 2)
        t["value"] = round(t["value"], 2)
        t["by_customer"] = {str(k): round(v, 2) for k, v in t["by_customer"].items() if abs(v) > 1e-9}

    # ---- quarters with the same quarter a year earlier
    quarter_rows = []
    for qb in quarters:
        u, v, _ = _sum_window(obs, qb.start, qb.end)
        ly_a, ly_b = cal.same_day_last_year(qb.start), cal.same_day_last_year(qb.end)
        lu, lv, _ = _sum_window(obs, ly_a, ly_b)
        quarter_rows.append(
            {
                **qb.as_dict(),
                "units": round(u, 2),
                "value": round(v, 2),
                "last_year_units": round(lu, 2),
                "last_year_value": round(lv, 2),
                "change_pct": _pct(u, lu),
                "partial": qb.end > f.date_to,
            }
        )

    # ---- top sellers
    by_product: dict[int, dict[str, Any]] = defaultdict(lambda: {"units": 0.0, "value": 0.0, "customers": set()})
    for o in in_window:
        sh = o.share(f.date_from, f.date_to)
        d = by_product[o.product_id]
        d["units"] += o.units * sh
        if o.value is not None:
            d["value"] += o.value * sh
        if o.units:
            d["customers"].add(o.customer_id)
    cmp_by_product: dict[int, float] = defaultdict(float)
    if cmp:
        for o in in_cmp:
            cmp_by_product[o.product_id] += o.units * o.share(cmp[0], cmp[1])
    top = sorted(by_product.items(), key=lambda kv: kv[1]["units"], reverse=True)[:TOP_N]
    top_sellers = [
        {
            "product_id": pid,
            "label": product_label(products.get(pid), pid),
            "sku": products[pid].sku if pid in products else None,
            "units": round(d["units"], 2),
            "value": round(d["value"], 2),
            "customers": len(d["customers"]),
            "compare_units": round(cmp_by_product.get(pid, 0.0), 2) if cmp else None,
            "change_pct": _pct(d["units"], cmp_by_product.get(pid, 0.0)) if cmp else None,
        }
        for pid, d in top
        if d["units"] > 0
    ]

    by_customer_units: dict[int, float] = defaultdict(float)
    for o in in_window:
        by_customer_units[o.customer_id] += o.units * o.share(f.date_from, f.date_to)

    coverage = _coverage(cal, f, obs, customer_ids, customers, cfg_by_customer, today)
    last_day = {row["customer_id"]: row["last_reported_day"] for row in coverage["customers"]}
    problems = _problems(obs, products, customers, cfg_by_customer, stock, last_day, f.date_to)

    out = {
        "filters": {
            "date_from": f.date_from.isoformat(),
            "date_to": f.date_to.isoformat(),
            "grain": f.grain,
            "compare": f.compare,
            "compare_from": cmp[0].isoformat() if cmp else None,
            "compare_to": cmp[1].isoformat() if cmp else None,
            "vat": f.vat,
            "vat_rate_pct": vat_rate,
            "customer_ids": f.customer_ids,
        },
        "calendar": {"type": cal.type, "label": cal.year(f.date_to).label},
        "kpis": {
            "units": round(units, 2),
            "value": round(value, 2),
            "value_estimated": round(est_value, 2),
            "units_without_price": round(units_no_value, 2),
            "compare_units": round(c_units, 2) if cmp else None,
            "compare_value": round(c_value, 2) if cmp else None,
            "units_change_pct": _pct(units, c_units) if cmp else None,
            "value_change_pct": _pct(value, c_value) if cmp else None,
            "stock_on_hand": round(soh_total, 2) if stock_customers else None,
            "stock_customers": len(stock_customers),
            "weekly_rate": round(sum(rate4_by_pair.values()), 2),
            "weeks_of_cover": round(soh_total / rate4_stocked, 1) if stock_customers and rate4_stocked > 0 else None,
            "skus_selling": sum(1 for d in by_product.values() if d["units"] > 0),
            "needs_replen": problems["counts"].get("needs_replen", 0),
            "out_of_stock": problems["counts"].get("out_of_stock", 0),
            "aged": problems["counts"].get("aged", 0),
        },
        "trend": trend,
        "quarters": quarter_rows,
        "top_sellers": top_sellers,
        "customer_split": sorted(
            (
                {
                    "customer_id": cid,
                    "name": customers[cid].name if cid in customers else f"Customer {cid}",
                    "units": round(u, 2),
                }
                for cid, u in by_customer_units.items()
                if abs(u) > 1e-9
            ),
            key=lambda r: r["units"],
            reverse=True,
        ),
        "coverage": coverage,
        "problems": problems,
        "notes": [],
    }
    finer = 1 if f.grain == "day" else 7 if f.grain == "week" else None
    if finer and any(o.days > finer for o in in_window):
        out["notes"].append(
            "Some customers report by week or month; those figures are spread evenly over their days in this view."
        )
    if units_no_value > 0:
        out["notes"].append(
            f"{units_no_value:,.0f} units have no sell price and no listing price, so they are not in sales value."
        )
    if est_value > 0:
        out["notes"].append("Some sales value uses the latest captured listing price (marked as estimated).")
    out["summary"] = summarize(out)
    return out


def _stock_positions(obs: list[Obs], as_of: date) -> dict[tuple[int, int], dict[str, Any]]:
    """Stock per (customer, product) on each customer's latest stock date on or before ``as_of``."""
    latest: dict[int, date] = {}
    last_row: dict[int, date] = {}
    for o in obs:
        if o.start > as_of:
            continue
        if o.customer_id not in last_row or o.end > last_row[o.customer_id]:
            last_row[o.customer_id] = o.end
        if o.soh is not None and (o.customer_id not in latest or o.start > latest[o.customer_id]):
            latest[o.customer_id] = o.start
    # A stock report older than five weeks before the customer's latest figures is no longer a position.
    latest = {c: d for c, d in latest.items() if d >= last_row[c] - timedelta(days=STOCK_STALE_DAYS)}
    out: dict[tuple[int, int], dict[str, Any]] = {}
    # Every product the customer reported in the lookback holds 0 unless its latest stock row says otherwise.
    for o in obs:
        if o.customer_id in latest and o.start <= as_of:
            out.setdefault((o.customer_id, o.product_id), {"soh": 0.0, "on_order": 0.0, "in_transit": 0.0, "date": latest[o.customer_id]})
    for o in obs:
        d = latest.get(o.customer_id)
        if d is not None and o.start == d and o.soh is not None:
            row = out[(o.customer_id, o.product_id)]
            row["soh"] += o.soh
            row["on_order"] += o.on_order
            row["in_transit"] += o.in_transit
    return out


def _coverage(
    cal: BusinessCalendar,
    f: OverviewFilters,
    obs: list[Obs],
    customer_ids: set[int],
    customers: dict[int, DimCustomer],
    cfgs: dict[int, CustomerReportConfig],
    today: date,
) -> dict[str, Any]:
    weeks_span = ((f.date_to - f.date_from).days + 1) / 7
    col_grain = "week" if weeks_span <= 27 else "month"
    cols = cal.buckets(f.date_from, f.date_to, col_grain)
    spans = _covered_intervals(obs)
    rows = []
    for cid in sorted(customer_ids, key=lambda c: (customers[c].name if c in customers else str(c)).lower()):
        cfg = cfgs.get(cid)
        expected = bool(cfg and cfg.reports_expected)
        cadence = (cfg.expected_cadence if cfg else None) or "weekly"
        threshold = int(cfg.overdue_threshold_days) if cfg and cfg.overdue_threshold_days is not None else 10
        cspans = spans.get(cid, [])
        last = max((e for _s, e in cspans), default=None)
        cells = []
        counts: dict[str, int] = defaultdict(int)
        for col in cols:
            if col.start > today:
                status, ratio = "future", None
            else:
                upto = min(col.end, today)
                need = (upto - col.start).days + 1
                have = _covered_days(cspans, col.start, upto)
                ratio = have / need if need else 0.0
                period_end = cal.bucket(col.end, "month").end if cadence == "monthly" else col.end
                due = period_end + timedelta(days=threshold)
                if ratio >= 0.999:
                    status = "received"
                elif not expected or cadence == "adhoc":
                    status = "partial" if ratio > 0 else "not_expected"
                elif ratio > 0:
                    status = "partial" if today > due else "due"
                else:
                    status = "missing" if today > due else "due"
            counts[status] += 1
            cells.append({"start": col.start.isoformat(), "status": status, "ratio": None if ratio is None else round(ratio, 3)})
        rows.append(
            {
                "customer_id": cid,
                "name": customers[cid].name if cid in customers else f"Customer {cid}",
                "code": customers[cid].code if cid in customers else None,
                "reports_expected": expected,
                "cadence": cadence,
                "last_reported_day": last.isoformat() if last else None,
                "days_since_last": (today - last).days if last else None,
                "cells": cells,
                "missing": counts.get("missing", 0),
                "partial": counts.get("partial", 0),
            }
        )
    return {
        "grain": col_grain,
        "columns": [c.as_dict() for c in cols],
        "customers": rows,
        "missing_cells": sum(r["missing"] for r in rows),
        "customers_missing": [r["name"] for r in rows if r["missing"] > 0],
    }


def _problems(
    obs: list[Obs],
    products: dict[int, DimProduct],
    customers: dict[int, DimCustomer],
    cfgs: dict[int, CustomerReportConfig],
    stock: dict[tuple[int, int], dict[str, Any]],
    last_day: dict[int, str | None],
    as_of: date,
) -> dict[str, Any]:
    anchors: dict[int, date] = {}
    for cid, d in last_day.items():
        anchors[cid] = min(as_of, date.fromisoformat(d)) if d else as_of
    weeks: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0] * LOOKBACK_WEEKS)
    for o in obs:
        anchor = anchors.get(o.customer_id, as_of)
        first = anchor - timedelta(days=LOOKBACK_WEEKS * 7 - 1)
        if o.end < first or o.start > anchor:
            continue
        series = weeks[(o.customer_id, o.product_id)]
        lo = max(0, ((o.start - first).days) // 7)
        hi = min(LOOKBACK_WEEKS - 1, ((min(o.end, anchor) - first).days) // 7)
        for i in range(lo, hi + 1):
            a = first + timedelta(days=7 * i)
            sh = o.share(a, a + timedelta(days=6))
            if sh > 0:
                series[i] += o.units * sh
    for key in stock:
        weeks.setdefault(key, [0.0] * LOOKBACK_WEEKS)

    rows = []
    counts: dict[str, int] = defaultdict(int)
    for (cid, pid), wk in weeks.items():
        prod = products.get(pid)
        st = stock.get((cid, pid))
        soh = st["soh"] if st else None
        recent = wk[-RECENT_WEEKS:]
        recent_rate = sum(recent) / RECENT_WEEKS
        prior = wk[-(RECENT_WEEKS + STREAK_WEEKS) : -RECENT_WEEKS]
        prior_rate = sum(prior) / STREAK_WEEKS
        prior_selling = sum(1 for u in prior if u > 0)
        last8 = sum(wk[-NO_SALES_WEEKS:])
        before = sum(wk[:-NO_SALES_WEEKS])
        last_sale_week = max((i for i, u in enumerate(wk) if u > 0), default=None)
        weeks_since_sale = (LOOKBACK_WEEKS - 1 - last_sale_week) if last_sale_week is not None else None
        ended = _is_ended(prod, as_of)
        cfg = cfgs.get(cid)
        min_woc = float(cfg.replen_min_weeks_of_cover) if cfg and cfg.replen_min_weeks_of_cover else DEFAULT_REPLEN_MIN_WEEKS_OF_COVER
        target_woc = float(cfg.replen_target_weeks_of_cover) if cfg and cfg.replen_target_weeks_of_cover else DEFAULT_REPLEN_TARGET_WEEKS_OF_COVER
        rate = recent_rate if recent_rate > 0 else (last8 / NO_SALES_WEEKS)
        woc = soh / rate if soh is not None and rate > 0 else None

        reason = detail = None
        suggested = None
        if soh is not None and soh <= 0 and last8 > 0 and not ended:
            reason = "out_of_stock"
            detail = f"0 in stock; was selling {last8 / NO_SALES_WEEKS:,.1f} a week"
            suggested = math.ceil(rate * target_woc - (st["on_order"] + st["in_transit"])) if st else None
        elif soh is not None and soh > 0 and rate > 0 and woc is not None and woc < min_woc and not ended:
            reason = "needs_replen"
            detail = f"{woc:,.1f} weeks of cover (replenish below {min_woc:g})"
            suggested = math.ceil(rate * target_woc - soh - st["on_order"] - st["in_transit"])
        elif prior_selling >= STREAK_MIN_SELLING_WEEKS and prior_rate >= DROP_MIN_UNITS_PER_WEEK and recent_rate <= prior_rate * DROP_RATIO:
            reason = "dropped"
            detail = f"{prior_rate:,.1f} a week for {STREAK_WEEKS} weeks, now {recent_rate:,.1f} a week"
        elif soh is not None and soh > 0 and last8 <= 0:
            reason = "aged"
            since = f"{weeks_since_sale} weeks" if weeks_since_sale is not None else f"over {LOOKBACK_WEEKS} weeks"
            detail = f"{soh:,.0f} in stock, no sales for {since}"
        elif last8 <= 0 and before > 0 and not ended:
            reason = "stopped"
            detail = f"No sales for {weeks_since_sale} weeks (sold {before:,.0f} before that)"
        if reason is None:
            continue
        counts[reason] += 1
        rows.append(
            {
                "reason": reason,
                "reason_label": REASON_LABELS[reason],
                "detail": detail,
                "customer_id": cid,
                "customer_name": customers[cid].name if cid in customers else f"Customer {cid}",
                "product_id": pid,
                "product": product_label(prod, pid),
                "sku": prod.sku if prod else None,
                "business_unit": prod.business_unit if prod else None,
                "category": prod.category if prod else None,
                "lifecycle": prod.lifecycle_status if prod else None,
                "stock_on_hand": round(soh, 2) if soh is not None else None,
                "on_order": round(st["on_order"] + st["in_transit"], 2) if st else None,
                "rate_recent": round(recent_rate, 2),
                "rate_before": round(prior_rate, 2),
                "weeks_of_cover": round(woc, 1) if woc is not None else None,
                "weeks_since_sale": weeks_since_sale,
                "suggested_qty": suggested if suggested and suggested > 0 else None,
                "judged_to": anchors.get(cid, as_of).isoformat(),
                "weekly_units": [round(u, 2) for u in wk],
            }
        )
    order = {r: i for i, r in enumerate(REASONS)}

    def impact(r: dict[str, Any]) -> float:
        if r["reason"] in ("out_of_stock", "needs_replen"):
            return -(r["suggested_qty"] or 0) - r["rate_recent"]
        if r["reason"] == "dropped":
            return -(r["rate_before"] - r["rate_recent"])
        return -(r["stock_on_hand"] or 0)

    rows.sort(key=lambda r: (order[r["reason"]], impact(r)))
    return {
        "counts": dict(counts),
        "rows": rows[:PROBLEM_ROW_LIMIT],
        "total": len(rows),
        "rules": {
            "recent_weeks": RECENT_WEEKS,
            "streak_weeks": STREAK_WEEKS,
            "streak_min_selling_weeks": STREAK_MIN_SELLING_WEEKS,
            "drop_ratio": DROP_RATIO,
            "no_sales_weeks": NO_SALES_WEEKS,
            "default_replen_min_weeks": DEFAULT_REPLEN_MIN_WEEKS_OF_COVER,
            "default_replen_target_weeks": DEFAULT_REPLEN_TARGET_WEEKS_OF_COVER,
        },
    }


def summarize(o: dict[str, Any]) -> list[str]:
    """Plain sentences from the computed numbers. Always available; no model involved."""
    lines: list[str] = []
    k = o["kpis"]
    cmp_name = {"prior_year": "the same period last year", "prior_period": "the period before"}.get(o["filters"]["compare"])
    if cmp_name and k["units_change_pct"] is not None:
        direction = "up" if k["units_change_pct"] >= 0 else "down"
        lines.append(f"Units sold {direction} {abs(k['units_change_pct']) * 100:.0f}% on {cmp_name} ({k['units']:,.0f} vs {k['compare_units']:,.0f}).")
    elif k["units"]:
        lines.append(f"{k['units']:,.0f} units sold in this window.")
    if o["top_sellers"]:
        t = o["top_sellers"][0]
        lines.append(f"Best seller: {t['label']} with {t['units']:,.0f} units across {t['customers']} customer(s).")
    pc = o["problems"]["counts"]
    parts = []
    for key in ("out_of_stock", "needs_replen", "dropped", "aged", "stopped"):
        if pc.get(key):
            parts.append(f"{pc[key]} {REASON_LABELS[key].lower()}")
    if parts:
        lines.append("SKUs needing attention: " + ", ".join(parts) + ".")
    drops = [r for r in o["problems"]["rows"] if r["reason"] == "dropped"]
    if drops:
        d = drops[0]
        lines.append(f"Biggest drop: {d['product']} at {d['customer_name']}, {d['detail']}.")
    missing = o["coverage"]["customers_missing"]
    if missing:
        names = ", ".join(missing[:4]) + (f" and {len(missing) - 4} more" if len(missing) > 4 else "")
        lines.append(f"Reports missing in this window: {names}.")
    return lines


def filter_options(session: Session, tenant_id: str) -> dict[str, Any]:
    """Customers, product groupings and data range for the filter bar."""
    s = FactCustomerSellthrough
    with_data = {
        int(r.customer_id): (r.first, r.last)
        for r in session.execute(
            select(s.customer_id, func.min(s.period_start_date).label("first"), func.max(s.period_start_date).label("last"))
            .where(s.tenant_id == tenant_id)
            .group_by(s.customer_id)
        )
    }
    reporting = {
        int(cfg.customer_id)
        for cfg in session.scalars(select(CustomerReportConfig).where(CustomerReportConfig.reports_expected.is_(True)))
    }
    key_accounts = {int(c) for c in session.scalars(select(DimCustomer.id).where(DimCustomer.is_key_account.is_(True)))}
    ids = set(with_data) | reporting | key_accounts
    custs = list(session.scalars(select(DimCustomer).where(DimCustomer.id.in_(ids or {-1}))))
    prod_ids = select(s.product_id).where(s.tenant_id == tenant_id).distinct().subquery()

    def distinct(col) -> list[str]:
        return sorted(
            str(v)
            for v in session.scalars(select(col).where(DimProduct.id.in_(select(prod_ids.c.product_id)), col.is_not(None)).distinct())
            if str(v).strip()
        )

    first = min((v[0] for v in with_data.values()), default=None)
    last = max((v[1] for v in with_data.values()), default=None)
    return {
        "customers": sorted(
            (
                {
                    "id": int(c.id),
                    "name": c.name,
                    "code": c.code,
                    "reports_expected": int(c.id) in reporting,
                    "has_data": int(c.id) in with_data,
                    "first_period": with_data[int(c.id)][0].isoformat() if int(c.id) in with_data else None,
                    "last_period": with_data[int(c.id)][1].isoformat() if int(c.id) in with_data else None,
                }
                for c in custs
            ),
            key=lambda c: (not c["has_data"], c["name"].lower()),
        ),
        "business_units": distinct(DimProduct.business_unit),
        "categories": distinct(DimProduct.category),
        "series": distinct(DimProduct.series_name),
        "first_period": first.isoformat() if first else None,
        "last_period": last.isoformat() if last else None,
    }


def period_presets(cal: BusinessCalendar, today: date) -> list[dict[str, str]]:
    """Quick period choices in the tenant calendar."""
    q = cal.bucket(today, "quarter")
    prev_q = cal.bucket(q.start - timedelta(days=1), "quarter")
    yr = cal.year(today)
    prev_yr = cal.year(yr.start - timedelta(days=1))
    week = cal.bucket(today, "week")
    last_full_week_end = week.start - timedelta(days=1)

    def p(key: str, label: str, a: date, b: date, grain: str) -> dict[str, str]:
        return {"key": key, "label": label, "date_from": a.isoformat(), "date_to": b.isoformat(), "grain": grain}

    return [
        p("last_4_weeks", "Last 4 weeks", last_full_week_end - timedelta(weeks=4) + timedelta(days=1), last_full_week_end, "day"),
        p("last_13_weeks", "Last 13 weeks", last_full_week_end - timedelta(weeks=13) + timedelta(days=1), last_full_week_end, "week"),
        p("quarter_to_date", f"{q.label} to date", q.start, today, "week"),
        p("last_quarter", prev_q.label, prev_q.start, prev_q.end, "week"),
        p("year_to_date", f"{yr.label} to date", yr.start, today, "month"),
        p("last_year", prev_yr.label, prev_yr.start, prev_yr.end, "month"),
        p("last_52_weeks", "Last 52 weeks", last_full_week_end - timedelta(weeks=52) + timedelta(days=1), last_full_week_end, "month"),
    ]
