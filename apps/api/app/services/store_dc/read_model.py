"""Read model: site grain where a label exists, account grain where it does not.

No distribution-centre section unless a steward has confirmed one.
Calculated stock is not written. Reported on-hand is the checkpoint.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment, FactInventoryDistributor
from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import served_customer_ids, tenant_config
from app.services.store_dc.rules import (
    COLLAPSED_NOTE,
    cover_weeks,
    inbound_leg,
    is_slow,
    is_unsold,
    is_weekly,
    need_units,
    norm_label,
    onward_leg,
    slow_multiple,
    stock_action_covers_site,
    stock_action_in_notes,
    suggestion_labels,
    unsold_window_weeks,
    weekly_rate,
    weeks_of_cover,
    window_count,
)


def _f(value: Any) -> float:
    return float(value or 0)


def _opt(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


class _Fact:
    __slots__ = ("customer_id", "product_id", "period", "grain", "kind", "units", "soh", "site")

    def __init__(self, customer_id, product_id, period, grain, kind, units, soh, site):
        self.customer_id = int(customer_id)
        self.product_id = int(product_id)
        self.period = period
        self.grain = grain
        self.kind = kind
        self.units = _f(units)
        self.soh = _opt(soh)
        self.site = (site or "").strip()


def _load_facts(db: Session, tenant_id: str, customer_ids: list[int]) -> list[_Fact]:
    if not customer_ids:
        return []
    rows = db.execute(
        select(
            FactCustomerSellthrough.customer_id,
            FactCustomerSellthrough.product_id,
            FactCustomerSellthrough.period_start_date,
            FactCustomerSellthrough.period_grain,
            FactCustomerSellthrough.period_type,
            FactCustomerSellthrough.units_sold,
            FactCustomerSellthrough.reported_soh,
            FactCustomerSellthrough.site_label,
        ).where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.customer_id.in_(customer_ids),
        )
    ).all()
    return [_Fact(*row) for row in rows]


def _latest_soh(rows: list[_Fact]) -> float | None:
    dated = [r for r in rows if r.soh is not None]
    if not dated:
        return None
    dated.sort(key=lambda r: r.period)
    return dated[-1].soh


def _weekly_totals(rows: list[_Fact]) -> list[tuple[date, float]]:
    buckets: dict[date, float] = defaultdict(float)
    for row in rows:
        if is_weekly(row.grain, row.kind):
            buckets[row.period] += row.units
    return sorted(buckets.items())


def _open_stock_actions(
    db: Session, tenant_id: str, customer_id: int
) -> dict[int, list[tuple[str, dict | None]]]:
    """Open promote, move, or return markers for this customer. A read, not a write.

    Each hit keeps the line's site list. A line written before sites were stored
    has no list and still covers every site.
    """
    from app.models.cpor import CporCase, CporCaseLine

    rows = db.execute(
        select(CporCaseLine.product_id, CporCase.notes, CporCaseLine.cost_evidence_json)
        .join(CporCase, CporCase.id == CporCaseLine.case_id)
        .where(
            CporCase.tenant_id == tenant_id,
            CporCase.customer_id == int(customer_id),
            CporCase.status.in_(("draft", "proposed", "approved", "active")),
        )
    ).all()
    found: dict[int, list[tuple[str, dict | None]]] = defaultdict(list)
    for product_id, notes, evidence in rows:
        action = stock_action_in_notes(notes)
        if action and product_id is not None:
            found[int(product_id)].append((action, evidence if isinstance(evidence, dict) else None))
    return found


def _taken_actions(
    executed: dict[int, list[tuple[str, dict | None]]] | None,
    product_id: int,
    site_label: str | None,
) -> set[str] | None:
    if executed is None:
        return None
    taken: set[str] = set()
    for action, evidence in executed.get(int(product_id), ()):
        if stock_action_covers_site(evidence, site_label):
            taken.add(action)
    return taken


def _executed_for(
    executed: dict[int, list[tuple[str, dict | None]]] | None,
    viewed_customer_id: int | None,
    owner_id: int | None,
) -> dict[int, list[tuple[str, dict | None]]] | None:
    """Open actions apply only to the customer who owns the stock."""
    if executed is None or viewed_customer_id is None or owner_id is None:
        return None
    if int(owner_id) != int(viewed_customer_id):
        return None
    return executed


def _line(
    rows: list[_Fact],
    *,
    product: DimProduct | None,
    product_id: int,
    cover: dict[str, Any],
    multiple: float,
    unsold_weeks: float,
    leg: dict[str, Any],
    executed_actions: set[str] | None = None,
) -> dict[str, Any]:
    weeks = _weekly_totals(rows)
    rate_n = min(4, len(weeks))
    rate_units = [units for _, units in weeks[-rate_n:]] if rate_n else []
    rate = weekly_rate(rate_units)
    soh = _latest_soh(rows)
    woc = weeks_of_cover(soh, rate)
    lead_weeks = float(leg["lead_time_weeks"] or 0)
    need = need_units(rate=rate, soh=soh, target_weeks=cover["target_weeks"], lead_weeks=lead_weeks)
    unsold_n = window_count(unsold_weeks)
    window_units = sum(units for _, units in weeks[-unsold_n:]) if weeks else 0.0
    slow = is_slow(woc, cover["target_weeks"], multiple)
    unsold = is_unsold(soh, window_units, len(weeks), unsold_weeks)
    taken = set(executed_actions or ())
    return {
        "product_id": product_id,
        "sku": product.sku if product else None,
        "product_name": product.name if product else None,
        "units_sold": round(sum(r.units for r in rows), 2),
        "stock_on_hand": None if soh is None else round(soh, 2),
        "weekly_rate": None if rate is None else round(rate, 4),
        "weeks_of_cover": None if woc is None else round(woc, 2),
        "need_units": need["units"],
        "need_reason": need["reason"],
        "lead_time_label": leg["lead_time_label"],
        "lead_time_weeks": leg["lead_time_weeks"],
        "lead_leg": leg["leg"],
        "slow": slow,
        "unsold": unsold,
        "suggestions": suggestion_labels(slow=slow, unsold=unsold),
        "suggestion_executed": bool(taken),
        "executed_actions": sorted(taken),
        "cover_min_weeks": cover["min_weeks"],
        "cover_target_weeks": cover["target_weeks"],
    }


def _group_products(rows: list[_Fact]) -> dict[int, list[_Fact]]:
    grouped: dict[int, list[_Fact]] = defaultdict(list)
    for row in rows:
        grouped[row.product_id].append(row)
    return grouped


def _site_block(
    rows: list[_Fact],
    *,
    site_label: str | None,
    customer_id: int,
    customer_name: str,
    supply: str,
    products: dict[int, DimProduct],
    cover: dict[str, Any],
    multiple: float,
    unsold_weeks: float,
    leg: dict[str, Any],
    executed: dict[int, list[tuple[str, dict | None]]] | None = None,
) -> dict[str, Any]:
    lines = [
        _line(
            group,
            product=products.get(pid),
            product_id=pid,
            cover=cover,
            multiple=multiple,
            unsold_weeks=unsold_weeks,
            leg=leg,
            executed_actions=_taken_actions(executed, pid, site_label),
        )
        for pid, group in sorted(_group_products(rows).items())
    ]
    need_values = [ln["need_units"] for ln in lines if ln["need_units"] is not None]
    soh_values = [ln["stock_on_hand"] for ln in lines if ln["stock_on_hand"] is not None]
    return {
        "site_label": site_label,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "supply": supply,
        "units_sold": round(sum(r.units for r in rows), 2),
        "stock_on_hand": None if not soh_values else round(sum(soh_values), 2),
        "need_units": None if not need_values else round(sum(need_values), 2),
        "lead_time_label": leg["lead_time_label"],
        "lines": lines,
    }


def _lead_index(db: Session, tenant_id: str, min_deliveries: int) -> dict[tuple[int, str], dict[str, Any]]:
    rows = db.execute(
        select(
            FactInboundShipment.distributor_id,
            FactInboundShipment.ship_to_raw,
            FactInboundShipment.ship_confirm_date,
            FactInboundShipment.pod_date,
        ).where(
            FactInboundShipment.tenant_id == tenant_id,
            FactInboundShipment.distributor_id.is_not(None),
            FactInboundShipment.ship_confirm_date.is_not(None),
            FactInboundShipment.pod_date.is_not(None),
            FactInboundShipment.line_state != "closed_superseded",
        )
    ).all()
    grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
    for distributor_id, ship_to, confirm, pod in rows:
        if pod < confirm:
            continue
        key = (int(distributor_id), norm_label(ship_to))
        grouped[key].append((pod - confirm).days)
    return {key: inbound_leg(days, min_deliveries) for key, days in grouped.items()}


def _distributors_for(db: Session, tenant_id: str, customer_ids: list[int]) -> list[dict[str, Any]]:
    if not customer_ids:
        return []
    counts = db.execute(
        select(FactInboundShipment.distributor_id, func.count())
        .where(
            FactInboundShipment.tenant_id == tenant_id,
            FactInboundShipment.distributor_id.is_not(None),
            FactInboundShipment.line_state != "closed_superseded",
            or_(
                FactInboundShipment.customer_id.in_(customer_ids),
                FactInboundShipment.resolved_customer_id.in_(customer_ids),
            ),
        )
        .group_by(FactInboundShipment.distributor_id)
    ).all()
    if not counts:
        return []
    ids = [int(i) for i, _ in counts]
    names = {
        int(i): (name, code)
        for i, name, code in db.execute(
            select(DimDistributor.id, DimDistributor.name, DimDistributor.code).where(DimDistributor.id.in_(ids))
        ).all()
    }
    stock_rows = db.execute(
        select(
            FactInventoryDistributor.distributor_id,
            FactInventoryDistributor.product_id,
            FactInventoryDistributor.on_hand_units,
            FactInventoryDistributor.as_of_date,
        ).where(
            FactInventoryDistributor.tenant_id == tenant_id,
            FactInventoryDistributor.distributor_id.in_(ids),
        )
    ).all()
    latest: dict[tuple[int, int], tuple[Any, float]] = {}
    for distributor_id, product_id, units, as_of in stock_rows:
        key = (int(distributor_id), int(product_id))
        prev = latest.get(key)
        if prev is None or as_of >= prev[0]:
            latest[key] = (as_of, float(units or 0))
    stock_sum: dict[int, float] = defaultdict(float)
    stock_as_of: dict[int, Any] = {}
    for (distributor_id, _), (as_of, units) in latest.items():
        stock_sum[distributor_id] += units
        if distributor_id not in stock_as_of or as_of > stock_as_of[distributor_id]:
            stock_as_of[distributor_id] = as_of
    out = []
    for distributor_id, lines in sorted(counts, key=lambda item: (-int(item[1]), int(item[0]))):
        name, code = names.get(int(distributor_id), (None, None))
        out.append(
            {
                "id": int(distributor_id),
                "name": name,
                "code": code,
                "shipment_lines": int(lines),
                "stock_on_hand": round(stock_sum[int(distributor_id)], 2) if int(distributor_id) in stock_sum else None,
                "stock_as_of": stock_as_of[int(distributor_id)].isoformat() if int(distributor_id) in stock_as_of else None,
                "stock_grain": "distributor",
            }
        )
    return out


def _primary_distributor(distributors: list[dict[str, Any]]) -> int | None:
    if not distributors:
        return None
    return int(distributors[0]["id"])


def _leg_for_site(
    index: dict[tuple[int, str], dict[str, Any]],
    distributor_id: int | None,
    site_norm: str,
    supply: str,
    min_deliveries: int,
) -> dict[str, Any]:
    if supply == "customer_dc":
        return onward_leg()
    if distributor_id is None or not site_norm:
        return inbound_leg([], min_deliveries)
    return index.get((distributor_id, site_norm)) or inbound_leg([], min_deliveries)


def _products(db: Session, ids: set[int]) -> dict[int, DimProduct]:
    if not ids:
        return {}
    rows = db.execute(select(DimProduct).where(DimProduct.id.in_(ids))).scalars().all()
    return {int(p.id): p for p in rows}


def _configs(db: Session, ids: list[int]) -> dict[int, CustomerReportConfig]:
    if not ids:
        return {}
    rows = db.execute(select(CustomerReportConfig).where(CustomerReportConfig.customer_id.in_(ids))).scalars().all()
    return {int(r.customer_id): r for r in rows}


def _confirmed_dcs(db: Session, tenant_id: str, customer_id: int) -> list[SiteCandidate]:
    rows = db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == tenant_id, SiteCandidate.status == "confirmed")
    ).scalars().all()
    out = []
    for row in rows:
        if row.blocked_as_distributor_site:
            continue
        if customer_id in served_customer_ids(db, tenant_id, row):
            out.append(row)
    return out


def _dc_section(
    db: Session,
    tenant_id: str,
    candidate: SiteCandidate,
    *,
    facts: list[_Fact],
    names: dict[int, str],
    products: dict[int, DimProduct],
    configs: dict[int, CustomerReportConfig],
    distributors: list[dict[str, Any]],
    lead_index: dict[tuple[int, str], dict[str, Any]],
    min_deliveries: int,
    executed: dict[int, list[tuple[str, dict | None]]] | None = None,
    viewed_customer_id: int | None = None,
) -> dict[str, Any]:
    served = served_customer_ids(db, tenant_id, candidate)
    owner_cfg = configs.get(candidate.customer_id) if candidate.customer_id else None
    owner_cover = cover_weeks(owner_cfg)
    owner_multiple = slow_multiple(owner_cfg)
    owner_unsold = unsold_window_weeks(owner_cfg, owner_cover["min_weeks"])
    distributor_id = _primary_distributor(distributors)
    dc_rows = [r for r in facts if norm_label(r.site) == candidate.site_label_norm]
    inbound = lead_index.get((distributor_id, candidate.site_label_norm)) if distributor_id else None
    if inbound is None:
        inbound = inbound_leg([], min_deliveries)
    flat = dc_rows
    dc_block = _site_block(
        flat,
        site_label=candidate.site_label,
        customer_id=candidate.customer_id or 0,
        customer_name=names.get(candidate.customer_id or 0, ""),
        supply="distributor",
        products=products,
        cover=owner_cover,
        multiple=owner_multiple,
        unsold_weeks=owner_unsold,
        leg=inbound,
        executed=_executed_for(executed, viewed_customer_id, candidate.customer_id),
    )
    stores = []
    store_need_by_product: dict[int, float] = defaultdict(float)
    for cid in served:
        cust_cover = cover_weeks(configs.get(cid))
        cust_rows = [r for r in facts if r.customer_id == cid and r.site and norm_label(r.site) != candidate.site_label_norm]
        by_site: dict[str, list[_Fact]] = defaultdict(list)
        labels: dict[str, str] = {}
        for row in cust_rows:
            key = norm_label(row.site)
            by_site[key].append(row)
            labels.setdefault(key, row.site)
        for key, group in sorted(by_site.items()):
            block = _site_block(
                group,
                site_label=labels[key],
                customer_id=cid,
                customer_name=names.get(cid, ""),
                supply="customer_dc",
                products=products,
                cover=cust_cover,
                multiple=slow_multiple(configs.get(cid)),
                unsold_weeks=unsold_window_weeks(configs.get(cid), cust_cover["min_weeks"]),
                leg=onward_leg(),
                executed=_executed_for(executed, viewed_customer_id, cid),
            )
            stores.append(block)
            for line in block["lines"]:
                if line["need_units"] is not None:
                    store_need_by_product[line["product_id"]] += float(line["need_units"])
    dc_soh_by_product = {ln["product_id"]: ln["stock_on_hand"] for ln in dc_block["lines"]}
    dc_rate_by_product = {ln["product_id"]: ln["weekly_rate"] for ln in dc_block["lines"]}
    dc_detail = {ln["product_id"]: ln for ln in dc_block["lines"]}
    product_ids = set(store_need_by_product) | set(dc_soh_by_product)
    from_distributor = []
    for pid in sorted(product_ids):
        soh = dc_soh_by_product.get(pid)
        rate = dc_rate_by_product.get(pid) or 0.0
        asking = round(store_need_by_product.get(pid, 0.0), 2)
        lead_weeks = float(inbound["lead_time_weeks"] or 0)
        if soh is None:
            units = None
            reason = "no stock reported"
        else:
            units = round(max(0.0, asking + rate * (owner_cover["target_weeks"] + lead_weeks) - soh), 2)
            reason = "stores_plus_cover" if lead_weeks == 0 else "stores_plus_cover_and_lead_time"
        detail = dc_detail.get(pid) or {}
        from_distributor.append(
            {
                "product_id": pid,
                "sku": products[pid].sku if pid in products else detail.get("sku"),
                "product_name": detail.get("product_name"),
                "stores_asking": asking,
                "stock_on_hand": soh,
                "need_units": units,
                "need_reason": reason,
                "lead_time_label": inbound["lead_time_label"],
                "weeks_of_cover": detail.get("weeks_of_cover"),
                "slow": bool(detail.get("slow")),
                "unsold": bool(detail.get("unsold")),
                "suggestions": list(detail.get("suggestions") or []),
                "suggestion_executed": bool(detail.get("suggestion_executed")),
                "executed_actions": list(detail.get("executed_actions") or []),
            }
        )
    stock_values = [ln["stock_on_hand"] for ln in dc_block["lines"] if ln["stock_on_hand"] is not None]
    return {
        "candidate_id": candidate.id,
        "customer_id": candidate.customer_id,
        "site_label": candidate.site_label,
        "serves": [{"customer_id": cid, "customer_name": names.get(cid)} for cid in served],
        "stock_on_hand": None if not stock_values else round(sum(stock_values), 2),
        "stock_note": None if stock_values else "no stock reported",
        "supply": "distributor",
        "lead_time": inbound,
        "onward": onward_leg(),
        "stores": stores,
        "need_from_distributor": from_distributor,
    }


def build_lead_index(db: Session, tenant_id: str) -> dict[tuple[int, str], dict[str, Any]]:
    """Tenant-wide inbound lead legs. A caller that builds many views builds this once."""
    cfg_row = tenant_config(db, tenant_id)
    return _lead_index(db, tenant_id, int(cfg_row["lead_time_min_deliveries"]))


def build_customer_view(
    db: Session,
    tenant_id: str,
    customer_id: int,
    *,
    lead_index: dict[tuple[int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    customer = db.get(DimCustomer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError(str(customer_id))
    executed = _open_stock_actions(db, tenant_id, customer_id)
    cfg_row = tenant_config(db, tenant_id)
    min_deliveries = int(cfg_row["lead_time_min_deliveries"])
    dcs = _confirmed_dcs(db, tenant_id, customer_id)
    served_ids = {customer_id}
    for dc in dcs:
        served_ids.update(served_customer_ids(db, tenant_id, dc))
    id_list = sorted(served_ids)
    facts = _load_facts(db, tenant_id, id_list)
    name_rows = db.execute(select(DimCustomer.id, DimCustomer.name).where(DimCustomer.id.in_(id_list))).all()
    names = {int(i): name for i, name in name_rows}
    products = _products(db, {r.product_id for r in facts})
    configs = _configs(db, id_list)
    own = [r for r in facts if r.customer_id == customer_id]
    labeled = [r for r in own if r.site]
    blank = [r for r in own if not r.site]
    distributors = _distributors_for(db, tenant_id, [customer_id])
    if lead_index is None:
        lead_index = _lead_index(db, tenant_id, min_deliveries)
    # Rebuild index legs with this tenant floor. _lead_index already used min_deliveries.
    distributor_id = _primary_distributor(distributors)
    own_cover = cover_weeks(configs.get(customer_id))
    own_multiple = slow_multiple(configs.get(customer_id))
    own_unsold = unsold_window_weeks(configs.get(customer_id), own_cover["min_weeks"])
    has_dc = bool(dcs)
    sections = [
        _dc_section(
            db,
            tenant_id,
            dc,
            facts=facts,
            names=names,
            products=products,
            configs=configs,
            distributors=distributors,
            lead_index=lead_index,
            min_deliveries=min_deliveries,
            executed=executed,
            viewed_customer_id=customer_id,
        )
        for dc in dcs
    ]
    dc_labels = {norm_label(dc.site_label) for dc in dcs}
    sites = []
    if labeled:
        by_site: dict[str, list[_Fact]] = defaultdict(list)
        labels: dict[str, str] = {}
        for row in labeled:
            key = norm_label(row.site)
            if key in dc_labels:
                continue
            by_site[key].append(row)
            labels.setdefault(key, row.site)
        for key, group in sorted(by_site.items()):
            supply = "customer_dc" if has_dc else "distributor"
            leg = _leg_for_site(lead_index, distributor_id, key, supply, min_deliveries)
            sites.append(
                _site_block(
                    group,
                    site_label=labels[key],
                    customer_id=customer_id,
                    customer_name=names.get(customer_id, customer.name),
                    supply=supply,
                    products=products,
                    cover=own_cover,
                    multiple=own_multiple,
                    unsold_weeks=own_unsold,
                    leg=leg,
                    executed=executed,
                )
            )
    collapsed = None
    account = None
    if labeled and blank:
        collapsed = {"units_sold": round(sum(r.units for r in blank), 2), "note": COLLAPSED_NOTE}
    elif not labeled:
        # No receiving site, so the inbound leg is not borrowed from another ship-to.
        leg = inbound_leg([], min_deliveries)
        account = _site_block(
            blank,
            site_label=None,
            customer_id=customer_id,
            customer_name=customer.name,
            supply="distributor",
            products=products,
            cover=own_cover,
            multiple=own_multiple,
            unsold_weeks=own_unsold,
            leg=leg,
            executed=executed,
        )
    grain = "store" if sites or labeled else "account"
    lead_times = []
    site_norms = {norm_label(s["site_label"]) for s in sites if s["site_label"]}
    site_norms.update(dc_labels)
    for dist in distributors:
        targets = sorted(site_norms) or [None]
        for site_norm in targets:
            inbound = (
                lead_index.get((dist["id"], site_norm)) or inbound_leg([], min_deliveries)
                if site_norm
                else inbound_leg([], min_deliveries)
            )
            lead_times.append(
                {
                    "distributor_id": dist["id"],
                    "distributor_name": dist["name"],
                    "receiving_site": site_norm,
                    "inbound": inbound,
                    "onward": onward_leg(),
                }
            )
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "customer_code": customer.code,
        "grain": grain,
        "supply": "distributor",
        "cover": own_cover,
        "distributors": distributors,
        "dc_sections": sections,
        "sites": sites,
        "account": account,
        "collapsed_grain": collapsed,
        "lead_times": lead_times,
        "lead_time_min_deliveries": min_deliveries,
    }


def set_customer_thresholds(
    db: Session,
    tenant_id: str,
    customer_id: int,
    *,
    slow_cover_multiple: float | None,
    unsold_weeks: float | None,
    set_slow: bool,
    set_unsold: bool,
) -> dict[str, Any]:
    customer = db.get(DimCustomer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError(str(customer_id))
    cfg = db.execute(
        select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
    ).scalar_one_or_none()
    if cfg is None:
        cfg = CustomerReportConfig(customer_id=customer_id, reports_expected=False)
        db.add(cfg)
    if set_slow:
        if slow_cover_multiple is not None and float(slow_cover_multiple) <= 0:
            raise ValueError("slow_cover_multiple must be greater than 0")
        cfg.slow_cover_multiple = None if slow_cover_multiple is None else float(slow_cover_multiple)
    if set_unsold:
        if unsold_weeks is not None and float(unsold_weeks) <= 0:
            raise ValueError("unsold_weeks must be greater than 0")
        cfg.unsold_weeks = None if unsold_weeks is None else float(unsold_weeks)
    db.flush()
    cover = cover_weeks(cfg)
    return {
        "customer_id": customer_id,
        "slow_cover_multiple": None if cfg.slow_cover_multiple is None else float(cfg.slow_cover_multiple),
        "unsold_weeks": None if cfg.unsold_weeks is None else float(cfg.unsold_weeks),
        "cover": cover,
    }


def list_board_customers(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    ids = set(
        db.execute(
            select(FactCustomerSellthrough.customer_id).where(FactCustomerSellthrough.tenant_id == tenant_id).distinct()
        ).scalars().all()
    )
    ids.update(
        db.execute(
            select(SiteCandidate.customer_id).where(
                SiteCandidate.tenant_id == tenant_id,
                SiteCandidate.customer_id.is_not(None),
            )
        ).scalars().all()
    )
    if not ids:
        return []
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name)
        .where(DimCustomer.tenant_id == tenant_id, DimCustomer.id.in_(ids))
        .order_by(DimCustomer.code.asc())
    ).all()
    return [{"id": int(i), "code": code, "name": name} for i, code, name in rows]
