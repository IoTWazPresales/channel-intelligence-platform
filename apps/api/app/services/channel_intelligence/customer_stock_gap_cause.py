"""Why a compared stock position differs (N-0110).

A gap can come from CIP's own data rather than the customer's stock. Each compared
position with a gap is given the first cause that applies, in this order:

- ``overwrite``: a sell-through row in the comparison holds two or more sites (or sale
  days) of one load in one stored row, because an older load keyed them as one and the
  last row won. Sales and on-hand are under-stated, so the gap is not the customer's.
- ``unmatched_shipment``: an over gap, and a shipped line for this product with a POD
  date in the window has no customer match, so it stays out of the expected position.
- ``no_pod``: an over gap, and a shipped line already matched to this customer and
  product has no POD date, shipped (or estimated to land) in the window.
- ``no_prior_on_hand``: a site reports on-hand now that did not in the previous report
  (or the reverse), so there is no starting on-hand for part of the position.
- ``repeated_report``: every product's units and on-hand in this report equal the previous
  report's, so the same figures were loaded as another period.
- ``unreported_weeks``: a short gap, and the window has periods with no sell-through report,
  so sales in them are unknown and the expected position is too high.
- ``unexplained``: none of the above. Only this is a stock-difference signal.

``causes`` lists every cause that applies. Read-only: no number is changed.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.services.channel_intelligence.customer_stock_gap import grain_of
from app.services.imports.parsers.customer_sell_through_grain import period_end

CAUSE_ORDER = (
    "overwrite",
    "unmatched_shipment",
    "no_pod",
    "no_prior_on_hand",
    "repeated_report",
    "unreported_weeks",
    "unexplained",
)

CAUSE_LABELS = {
    "overwrite": "Data gap: an older load stored several sites as one row",
    "unmatched_shipment": "Data gap: a delivered shipment has no customer match",
    "no_pod": "Data gap: a shipment to this customer has no proof-of-delivery date",
    "no_prior_on_hand": "Data gap: a site has no previous on-hand to start from",
    "repeated_report": "Data gap: this report repeats the previous report's figures",
    "unreported_weeks": "Data gap: sales for part of this window were not reported",
    "unexplained": "Stock difference: no data gap found",
}


@dataclass
class _FactRow:
    product_id: int
    grain: str
    start: date
    end: date
    site: str
    has_on_hand: bool
    collapsed_sites: bool = False
    collapsed_days: bool = False


@dataclass
class GapCause:
    cause: str
    causes: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return CAUSE_LABELS[self.cause]

    @property
    def is_data_gap(self) -> bool:
        return self.cause != "unexplained"


def _site_part(source_key: str) -> str:
    """``ct:{customer}:{site}:{product}:{period}``; the site part may itself hold a colon."""
    body = source_key.split(":", 2)[2] if source_key.count(":") >= 4 else ""
    return body.rsplit(":", 2)[0] if body else ""


def _fact_rows(db: Session, tenant_id: str, customer_id: int, product_ids: list[int]) -> list[_FactRow]:
    # Source rows of the load that last wrote each stored row: how many sites / sale days it holds.
    s = ImportCustomerSellthroughStagingLine
    f = FactCustomerSellthrough
    lines = (
        select(
            s.fact_sellthrough_row_id.label("fact_id"),
            s.import_job_id.label("job_id"),
            func.count(func.distinct(func.coalesce(s.site_label, s.raw_location_token))).label("sites"),
            func.count(func.distinct(s.raw_period_ref)).label("refs"),
            func.count(func.distinct(s.period_grain)).label("grains"),
        )
        .where(s.fact_sellthrough_row_id.isnot(None))
        .group_by(s.fact_sellthrough_row_id, s.import_job_id)
        .subquery()
    )
    rows = db.execute(
        select(
            f.product_id,
            f.period_grain,
            f.period_type,
            f.period_start_date,
            f.source_key,
            f.reported_soh,
            lines.c.sites,
            lines.c.refs,
        )
        .outerjoin(lines, (lines.c.fact_id == f.id) & (lines.c.job_id == f.import_job_id))
        .where(f.tenant_id == tenant_id, f.customer_id == int(customer_id), f.product_id.in_(product_ids))
    ).all()
    out = []
    for r in rows:
        grain = grain_of(r.period_grain, r.period_type)
        out.append(
            _FactRow(
                product_id=int(r.product_id),
                grain=grain,
                start=r.period_start_date,
                end=period_end(r.period_start_date, grain),
                site=_site_part(r.source_key),
                has_on_hand=r.reported_soh is not None,
                collapsed_sites=int(r.sites or 0) >= 2,
                # A day-grain source row carries its sale date in raw_period_ref; two refs in a
                # day-grain stored row would be two days. None exist before N-0110.
                collapsed_days=grain == "day" and int(r.refs or 0) >= 2,
            )
        )
    return out


def _report_periods(db: Session, tenant_id: str, customer_id: int) -> dict[tuple[str, date], tuple[date, str]]:
    """Every report period of a customer: (grain, start) -> (end, signature of all its figures)."""
    f = FactCustomerSellthrough
    rows = db.execute(
        select(f.period_grain, f.period_type, f.period_start_date, f.product_id, f.source_key, f.units_sold, f.reported_soh)
        .where(f.tenant_id == tenant_id, f.customer_id == int(customer_id))
    ).all()
    figures: dict[tuple[str, date], list[tuple[int, str, str]]] = defaultdict(list)
    for pg, pt, start, pid, sk, units, soh in rows:
        # The site and product, not the date, identify a figure across periods.
        site_product = sk.rsplit(":", 1)[0] if sk else str(pid)
        figures[(grain_of(pg, pt), start)].append((int(pid), site_product, f"{units}:{soh}"))
    out: dict[tuple[str, date], tuple[date, str]] = {}
    for (grain, start), items in figures.items():
        sig = hashlib.md5(repr(sorted(items)).encode("utf-8")).hexdigest()  # noqa: S324 - equality only
        out[(grain, start)] = (period_end(start, grain), sig)
    return out


def _periods_in(days: int, grain: str) -> int:
    if grain == "day":
        return days
    if grain == "month":
        return max(1, round(days / 30.4))
    return max(1, -(-days // 7))


def _shipments(db: Session, tenant_id: str, product_ids: list[int]) -> list[Any]:
    sh = FactInboundShipment
    return db.execute(
        select(
            sh.product_id,
            sh.resolved_customer_id,
            sh.pod_date,
            func.coalesce(sh.est_pod_date, sh.eta_date, sh.ship_confirm_date).label("landed_guess"),
            sh.quantity,
        ).where(
            sh.tenant_id == tenant_id,
            sh.product_id.in_(product_ids),
            func.lower(sh.line_state) == "shipped",
        )
    ).all()


def classify_gap_causes(db: Session, *, tenant_id: str, positions: Iterable[dict[str, Any]]) -> dict[int, GapCause]:
    """Cause per compared position id with a non-zero gap. ``positions`` are list rows."""
    todo = [p for p in positions if p.get("status") == "compared" and p.get("gap_units")]
    by_customer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in todo:
        by_customer[int(p["customer_id"])].append(p)
    all_products = sorted({int(p["product_id"]) for p in todo})
    shipments = _shipments(db, tenant_id, all_products) if all_products else []
    ship_by_product: dict[int, list[Any]] = defaultdict(list)
    for sh in shipments:
        ship_by_product[int(sh.product_id)].append(sh)

    out: dict[int, GapCause] = {}
    for customer_id, plist in by_customer.items():
        products = sorted({int(p["product_id"]) for p in plist})
        facts = _fact_rows(db, tenant_id, customer_id, products)
        reports = _report_periods(db, tenant_id, customer_id)
        facts_by_product: dict[int, list[_FactRow]] = defaultdict(list)
        for fr in facts:
            facts_by_product[fr.product_id].append(fr)
        for p in plist:
            pid = int(p["product_id"])
            grain = p["period_grain"]
            start = date.fromisoformat(p["period_start_date"])
            end = date.fromisoformat(p["period_end_date"])
            prev_end = date.fromisoformat(p["previous_period_end_date"])
            gap = float(p["gap_units"])
            pfacts = facts_by_product.get(pid, [])
            this_point = [fr for fr in pfacts if fr.grain == grain and fr.start == start and fr.has_on_hand]
            prev_point = [fr for fr in pfacts if fr.end == prev_end and fr.has_on_hand]
            in_window = [fr for fr in pfacts if prev_end < fr.end <= end]

            causes: list[str] = []
            detail: dict[str, Any] = {}
            collapsed = [fr for fr in this_point + prev_point + in_window if fr.collapsed_sites or fr.collapsed_days]
            if collapsed:
                causes.append("overwrite")
                detail["overwrite_rows"] = len({(fr.start, fr.site) for fr in collapsed})
                detail["overwrite_by"] = "day" if any(fr.collapsed_days for fr in collapsed) else "site"
            if gap > 0:
                unmatched = [
                    sh
                    for sh in ship_by_product.get(pid, [])
                    if sh.resolved_customer_id is None and sh.pod_date is not None and prev_end < sh.pod_date <= end
                ]
                if unmatched:
                    causes.append("unmatched_shipment")
                    detail["unmatched_units"] = float(sum(float(sh.quantity or 0) for sh in unmatched))
                no_pod = [
                    sh
                    for sh in ship_by_product.get(pid, [])
                    if sh.resolved_customer_id == customer_id
                    and sh.pod_date is None
                    and sh.landed_guess is not None
                    and prev_end < sh.landed_guess <= end
                ]
                if no_pod:
                    causes.append("no_pod")
                    detail["no_pod_units"] = float(sum(float(sh.quantity or 0) for sh in no_pod))
            now_sites = {fr.site for fr in this_point}
            prev_sites = {fr.site for fr in prev_point}
            if now_sites != prev_sites:
                causes.append("no_prior_on_hand")
                detail["sites_without_prior"] = len(now_sites - prev_sites)
                detail["sites_dropped"] = len(prev_sites - now_sites)
            this_sig = reports.get((grain, start), (None, None))[1]
            prev_sigs = [sig for (_, _), (pend, sig) in reports.items() if pend == prev_end]
            if this_sig is not None and this_sig in prev_sigs:
                causes.append("repeated_report")
            if gap < 0:
                reported = {pend for (g, _), (pend, _) in reports.items() if g == grain and prev_end < pend <= end}
                due = _periods_in((end - prev_end).days, grain)
                if len(reported) < due:
                    causes.append("unreported_weeks")
                    detail["periods_due"] = due
                    detail["periods_reported"] = len(reported)
            if not causes:
                causes.append("unexplained")
            out[int(p["id"])] = GapCause(cause=causes[0], causes=causes, detail=detail)
    return out
