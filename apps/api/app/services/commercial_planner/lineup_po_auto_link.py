"""PO↔lineup auto-link proposal engine (Unit 3). Derived on read — proposes only, never confirms.

Matches inbound shipment facts to lineup cases on ``resolved_customer_id`` + ``product_id`` + period.
Shipped totals use ``fact_inbound_shipment`` (``source_key`` deduped, latest-job-wins); open pipeline
is reported separately. Period anchor is **CRAD-primary** (``crad_date``); fallback ``schedule_ship_date``
then ``ship_confirm_date`` when CRAD is absent.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine, CommercialLineupPoAutoLinkDismiss
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder

logger = logging.getLogger(__name__)

ConfidenceTier = Literal["high", "medium"]
DateSource = Literal["crad", "schedule_ship", "ship_confirm", "none"]
CustomerAlign = Literal["exact", "unresolved", "mismatch"]


def quarter_bounds_from_period_start(period_start: date) -> tuple[date, date]:
    """Inclusive start, exclusive end for the calendar quarter of ``period_start``."""
    q = (period_start.month - 1) // 3 + 1
    start_month = 3 * (q - 1) + 1
    start = date(period_start.year, start_month, 1)
    if q == 4:
        end = date(period_start.year + 1, 1, 1)
    else:
        end = date(period_start.year, start_month + 3, 1)
    return start, end


def evidence_date_for_period_match(
    *,
    crad_date: date | None,
    schedule_ship_date: date | None,
    ship_confirm_date: date | None,
) -> tuple[date | None, DateSource]:
    if crad_date is not None:
        return crad_date, "crad"
    if schedule_ship_date is not None:
        return schedule_ship_date, "schedule_ship"
    if ship_confirm_date is not None:
        return ship_confirm_date, "ship_confirm"
    return None, "none"


def date_in_case_period(evidence_date: date | None, period_start: date | None) -> bool:
    if evidence_date is None or period_start is None:
        return False
    start, end = quarter_bounds_from_period_start(period_start)
    return start <= evidence_date < end


def classify_customer_alignment(
    resolved_customer_id: int | None,
    lineup_customer_id: int | None,
) -> CustomerAlign:
    if resolved_customer_id is not None and lineup_customer_id is not None:
        return "exact" if int(resolved_customer_id) == int(lineup_customer_id) else "mismatch"
    return "unresolved"


def classify_match_confidence(
    *,
    customer_align: CustomerAlign,
    date_source: DateSource,
    in_period: bool,
) -> tuple[ConfidenceTier | None, str | None]:
    if customer_align == "mismatch" or not in_period or date_source == "none":
        return None, None
    if customer_align == "exact" and date_source == "crad":
        return "high", "customer_product_crad_in_period"
    if customer_align == "exact" and date_source in ("schedule_ship", "ship_confirm"):
        return "medium", "customer_product_date_fallback_in_period"
    if customer_align == "unresolved":
        return "medium", "product_period_customer_unresolved"
    return None, None


@dataclass
class _ProductMatch:
    product_id: int
    planned_units: float = 0.0
    shipped_units: float = 0.0
    open_order_units: float = 0.0


@dataclass
class _ProposalAcc:
    case_id: int
    customer_id: int | None
    distributor_id: int | None
    po_number_norm: str
    purchase_order_id: int
    confidence: ConfidenceTier
    reason: str
    date_source: DateSource
    products: dict[int, _ProductMatch] = field(default_factory=dict)
    po_ids_seen: set[int] = field(default_factory=set)

    def proposal_key(self) -> str:
        return f"{self.case_id}:{self.customer_id or 0}:{self.po_number_norm}"


def _po_norm_already_linked_anywhere(
    po_number_norm: str,
    linked_pairs: set[tuple[int, int]],
    po_norm_by_id: dict[int, str],
) -> bool:
    """True when this PO norm is linked to any lineup case (not only the proposal case)."""
    for _linked_case_id, linked_po_id in linked_pairs:
        if po_norm_by_id.get(linked_po_id) == po_number_norm:
            return True
    return False


def _case_norm_already_linked(
    case_id: int,
    po_number_norm: str,
    linked_pairs: set[tuple[int, int]],
    po_norm_by_id: dict[int, str],
) -> bool:
    for linked_case_id, linked_po_id in linked_pairs:
        if linked_case_id == case_id and po_norm_by_id.get(linked_po_id) == po_number_norm:
            return True
    return False


def _pick_canonical_po_id(
    po_ids: set[int],
    po_meta: dict[int, PurchaseOrder],
    *,
    preferred_distributor_id: int | None,
) -> int:
    """Prefer distributor-assigned PO row over legacy NULL-dist duplicate."""
    if not po_ids:
        raise ValueError("po_ids required")
    if preferred_distributor_id is not None:
        for pid in sorted(po_ids):
            po = po_meta.get(pid)
            if po is not None and po.distributor_id == preferred_distributor_id:
                return pid
    for pid in sorted(po_ids):
        po = po_meta.get(pid)
        if po is not None and po.distributor_id is not None:
            return pid
    return min(po_ids)


def _best_lineup_match_for_product(
    case_lines: list[CommercialLineupLine],
    *,
    product_id: int,
    ship_customer_id: int | None,
    date_source: DateSource,
) -> tuple[CommercialLineupLine | None, ConfidenceTier | None, str | None, CustomerAlign | None]:
    """Return at most one lineup line match per shipment product (avoids duplicate qty)."""
    best_line: CommercialLineupLine | None = None
    best_align: CustomerAlign | None = None
    best_conf: ConfidenceTier | None = None
    best_reason: str | None = None

    for ln in case_lines:
        if int(ln.product_id) != product_id:  # type: ignore[arg-type]
            continue
        lineup_cust = int(ln.customer_id) if ln.customer_id is not None else None
        align = classify_customer_alignment(ship_customer_id, lineup_cust)
        conf, reason = classify_match_confidence(
            customer_align=align,
            date_source=date_source,
            in_period=True,
        )
        if conf is None:
            continue
        if best_line is None:
            best_line, best_align, best_conf, best_reason = ln, align, conf, reason
            continue
        # Prefer exact customer match over unresolved when both qualify.
        if best_align != "exact" and align == "exact":
            best_line, best_align, best_conf, best_reason = ln, align, conf, reason
        elif align == best_align and conf == "high" and best_conf == "medium":
            best_line, best_align, best_conf, best_reason = ln, align, conf, reason

    if best_line is None:
        return None, None, None, None
    return best_line, best_conf, best_reason, best_align


def _period_label_matches(case: CommercialLineupCase, period_filter: str | None) -> bool:
    if not period_filter or not str(period_filter).strip():
        return True
    needle = str(period_filter).strip().lower()
    label = (case.period_label or "").strip().lower()
    if label and needle in label:
        return True
    start = case.inferred_period_start
    if start is not None:
        q = (start.month - 1) // 3 + 1
        yy = str(start.year)[-2:]
        if needle in f"{yy}q{q}" or needle in f"{start.year}q{q}":
            return True
    return False


async def po_auto_link_proposals(
    db: AsyncSession,
    *,
    period: str | None = None,
    customer_id: int | None = None,
    confidence: ConfidenceTier | None = None,
    limit: int = 500,
    include_dismissed: bool = False,
) -> dict[str, Any]:
    """Build auto-link proposals (read-only; does not write ``commercial_lineup_case_po``)."""
    try:
        return await _po_auto_link_proposals_inner(
            db,
            period=period,
            customer_id=customer_id,
            confidence=confidence,
            limit=limit,
            include_dismissed=include_dismissed,
        )
    except Exception:
        logger.exception("po-auto-link proposals failed")
        return {"proposals": [], "total": 0, "data_unavailable": True, "dismissed": []}


async def _po_auto_link_proposals_inner(
    db: AsyncSession,
    *,
    period: str | None,
    customer_id: int | None,
    confidence: ConfidenceTier | None,
    limit: int,
    include_dismissed: bool,
) -> dict[str, Any]:
    cases = list(
        (
            await db.execute(
                select(CommercialLineupCase).where(CommercialLineupCase.commercial_status != "cancelled")
            )
        )
        .scalars()
        .all()
    )
    cases = [c for c in cases if _period_label_matches(c, period)]
    if not cases:
        return {"proposals": [], "total": 0, "data_unavailable": False, "dismissed": []}

    dismissed_rows: list[CommercialLineupPoAutoLinkDismiss] = []
    try:
        async with db.begin_nested():
            dismissed_rows = list(
                (await db.execute(select(CommercialLineupPoAutoLinkDismiss))).scalars().all()
            )
    except Exception:
        logger.warning("po-auto-link dismiss table unavailable — showing all proposals", exc_info=True)
    dismissed_keys = {str(r.proposal_key) for r in dismissed_rows}
    dismissed_out = [
        {
            "proposal_key": r.proposal_key,
            "case_id": int(r.case_id),
            "purchase_order_id": int(r.purchase_order_id),
            "reason_code": r.reason_code,
        }
        for r in dismissed_rows
    ]

    case_ids = [int(c.id) for c in cases]
    case_by_id = {int(c.id): c for c in cases}

    lineup_rows = (
        await db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.case_id.in_(case_ids),
                CommercialLineupLine.product_id.isnot(None),
            )
        )
    ).scalars().all()

    linked_pairs: set[tuple[int, int]] = set()
    for case_id, po_id in (
        await db.execute(select(CommercialLineupCasePo.case_id, CommercialLineupCasePo.purchase_order_id))
    ).all():
        linked_pairs.add((int(case_id), int(po_id)))

    # Truth layer: global ``source_key`` upsert (latest-job-wins). Evidence rows are per-job and
    # must not be summed for shipped totals — see ``shipment_inbound_facts.upsert_inbound_shipment_facts_for_job``.
    shipment_rows = (
        await db.execute(
            select(FactInboundShipment).where(
                FactInboundShipment.purchase_order_id.isnot(None),
                FactInboundShipment.product_id.isnot(None),
            )
        )
    ).scalars().all()

    ship_po_ids = sorted({int(s.purchase_order_id) for s in shipment_rows if s.purchase_order_id is not None})
    linked_po_ids = sorted({po_id for _cid, po_id in linked_pairs})
    all_po_ids = sorted(set(ship_po_ids) | set(linked_po_ids))
    po_meta: dict[int, PurchaseOrder] = {}
    po_norm_by_id: dict[int, str] = {}
    if all_po_ids:
        for po in (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id.in_(all_po_ids)))).scalars().all():
            pid = int(po.id)
            po_meta[pid] = po
            po_norm_by_id[pid] = (po.po_number_norm or po.po_number_raw or str(pid)).strip()

    # Lineup index: case_id -> list of lines; product_id -> lines on case
    lineup_by_case: dict[int, list[CommercialLineupLine]] = defaultdict(list)
    lineup_by_case_product: dict[tuple[int, int], list[CommercialLineupLine]] = defaultdict(list)
    planned_by_case_customer_product: dict[tuple[int, int, int], float] = defaultdict(float)
    for ln in lineup_rows:
        cid = int(ln.case_id)
        pid = int(ln.product_id)  # type: ignore[arg-type]
        lineup_by_case[cid].append(ln)
        lineup_by_case_product[(cid, pid)].append(ln)
        if ln.customer_id is not None:
            planned_by_case_customer_product[(cid, int(ln.customer_id), pid)] += float(ln.quantity_units or 0)

    proposals_map: dict[str, _ProposalAcc] = {}

    for ship in shipment_rows:
        po_id = int(ship.purchase_order_id)  # type: ignore[arg-type]
        po_number_norm = po_norm_by_id.get(po_id)
        if not po_number_norm:
            continue
        product_id = int(ship.product_id)  # type: ignore[arg-type]
        ship_cust = int(ship.resolved_customer_id) if ship.resolved_customer_id is not None else None
        ship_dist = int(ship.resolved_distributor_id) if ship.resolved_distributor_id is not None else None
        ship_qty = float(ship.quantity or 0)
        line_state = (ship.line_state or "").strip().lower()
        ev_date, date_src = evidence_date_for_period_match(
            crad_date=ship.crad_date,
            schedule_ship_date=ship.schedule_ship_date,
            ship_confirm_date=ship.ship_confirm_date,
        )

        if _po_norm_already_linked_anywhere(po_number_norm, linked_pairs, po_norm_by_id):
            continue

        for case_id, case_lines in lineup_by_case.items():
            case = case_by_id[case_id]
            period_start = case.inferred_period_start
            if not date_in_case_period(ev_date, period_start):
                continue

            product_lines = lineup_by_case_product.get((case_id, product_id), [])
            if not product_lines:
                continue

            match_ln, conf, reason, _align = _best_lineup_match_for_product(
                case_lines,
                product_id=product_id,
                ship_customer_id=ship_cust,
                date_source=date_src,
            )
            if match_ln is None or conf is None or reason is None:
                continue
            lineup_cust = int(match_ln.customer_id) if match_ln.customer_id is not None else None
            prop_cust = ship_cust if ship_cust is not None else lineup_cust
            lineup_dist = int(match_ln.distributor_id) if match_ln.distributor_id is not None else None
            dist_id = ship_dist if ship_dist is not None else lineup_dist
            if customer_id is not None and prop_cust is not None and int(prop_cust) != int(customer_id):
                continue
            if confidence is not None and conf != confidence:
                continue

            key = f"{case_id}:{prop_cust or 0}:{po_number_norm}"
            if key in dismissed_keys and not include_dismissed:
                continue

            existing = proposals_map.get(key)
            if existing is None:
                existing = _ProposalAcc(
                    case_id=case_id,
                    customer_id=prop_cust,
                    distributor_id=dist_id,
                    po_number_norm=po_number_norm,
                    purchase_order_id=po_id,
                    confidence=conf,
                    reason=reason,
                    date_source=date_src,
                )
                proposals_map[key] = existing
            else:
                if existing.confidence == "medium" and conf == "high":
                    existing.confidence = conf
                    existing.reason = reason
                    existing.date_source = date_src
                if existing.distributor_id is None and dist_id is not None:
                    existing.distributor_id = dist_id

            existing.po_ids_seen.add(po_id)
            pm = existing.products.setdefault(product_id, _ProductMatch(product_id=product_id))
            if line_state == "shipped":
                pm.shipped_units += ship_qty
            elif line_state == "open_order":
                pm.open_order_units += ship_qty
            if prop_cust is not None:
                pm.planned_units = planned_by_case_customer_product.get(
                    (case_id, int(prop_cust), product_id),
                    0.0,
                )

    for acc in proposals_map.values():
        acc.purchase_order_id = _pick_canonical_po_id(
            acc.po_ids_seen,
            po_meta,
            preferred_distributor_id=acc.distributor_id,
        )

    product_ids = sorted({m.product_id for acc in proposals_map.values() for m in acc.products.values()})
    prod_meta: dict[int, dict[str, str | None]] = {}
    if product_ids:
        for pid, sku, smn, mname in (
            await db.execute(
                select(
                    DimProduct.id,
                    DimProduct.sku,
                    DimProduct.sales_model_name,
                    DimProduct.marketing_name,
                ).where(DimProduct.id.in_(product_ids))
            )
        ).all():
            prod_meta[int(pid)] = {
                "sku": str(sku) if sku is not None else None,
                "sales_model_name": str(smn) if smn is not None else None,
                "marketing_name": str(mname) if mname is not None else None,
            }

    cust_ids = sorted({p.customer_id for p in proposals_map.values() if p.customer_id is not None})
    dist_ids = sorted({p.distributor_id for p in proposals_map.values() if p.distributor_id is not None})
    cust_names: dict[int, str] = {}
    dist_names: dict[int, tuple[str, str]] = {}
    if cust_ids:
        for cid, code, name in (
            await db.execute(
                select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(DimCustomer.id.in_(cust_ids))
            )
        ).all():
            cust_names[int(cid)] = f"{code} — {name}"
    if dist_ids:
        for did, code, name in (
            await db.execute(
                select(DimDistributor.id, DimDistributor.code, DimDistributor.name).where(
                    DimDistributor.id.in_(dist_ids)
                )
            )
        ).all():
            dist_names[int(did)] = (str(code), str(name))

    out: list[dict[str, Any]] = []
    for acc in sorted(
        proposals_map.values(),
        key=lambda p: (
            0 if p.confidence == "high" else 1,
            -(sum(x.shipped_units for x in p.products.values())),
            p.case_id,
        ),
    ):
        case = case_by_id[acc.case_id]
        po = po_meta.get(acc.purchase_order_id)
        products = sorted(acc.products.values(), key=lambda x: x.product_id)
        out.append(
            {
                "proposal_key": acc.proposal_key(),
                "case_id": acc.case_id,
                "case_period_label": case.period_label,
                "inferred_period_start": case.inferred_period_start.isoformat()
                if case.inferred_period_start
                else None,
                "customer_id": acc.customer_id,
                "customer_label": cust_names.get(int(acc.customer_id)) if acc.customer_id else None,
                "distributor_id": acc.distributor_id,
                "distributor_code": dist_names.get(int(acc.distributor_id), (None, None))[0]
                if acc.distributor_id
                else None,
                "distributor_name": dist_names.get(int(acc.distributor_id), (None, None))[1]
                if acc.distributor_id
                else None,
                "purchase_order_id": acc.purchase_order_id,
                "po_number": po.po_number_raw if po else None,
                "po_number_norm": po.po_number_norm if po else None,
                "confidence": acc.confidence,
                "reason": acc.reason,
                "date_source": acc.date_source,
                "already_linked": _case_norm_already_linked(
                    acc.case_id, acc.po_number_norm, linked_pairs, po_norm_by_id
                ),
                "alternate_purchase_order_ids": sorted(acc.po_ids_seen - {acc.purchase_order_id}),
                "dismissed": acc.proposal_key() in dismissed_keys,
                "matched_products": [
                    {
                        "product_id": m.product_id,
                        "sku": prod_meta.get(m.product_id, {}).get("sku"),
                        "sales_model_name": prod_meta.get(m.product_id, {}).get("sales_model_name"),
                        "marketing_name": prod_meta.get(m.product_id, {}).get("marketing_name"),
                        "planned_units": round(m.planned_units, 4),
                        "shipped_units": round(m.shipped_units, 4),
                        "open_order_units": round(m.open_order_units, 4),
                    }
                    for m in products
                ],
                "total_planned_units": round(sum(m.planned_units for m in products), 4),
                "total_shipped_units": round(sum(m.shipped_units for m in products), 4),
                "total_open_order_units": round(sum(m.open_order_units for m in products), 4),
            }
        )

    total = len(out)
    if limit > 0:
        out = out[: int(limit)]

    return {
        "proposals": out,
        "total": total,
        "returned": len(out),
        "data_unavailable": False,
        "dismissed": dismissed_out if include_dismissed else [],
        "dismissed_count": len(dismissed_keys),
    }
