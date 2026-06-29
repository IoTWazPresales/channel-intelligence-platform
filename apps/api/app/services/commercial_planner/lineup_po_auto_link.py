"""PO↔lineup auto-link proposal engine (Unit 3). Derived on read — proposes only, never confirms.

Matches shipment evidence to lineup cases on ``resolved_customer_id`` + ``product_id`` + period.
Period anchor is **CRAD-primary** (``crad_date``); fallback ``schedule_ship_date`` then
``ship_confirm_date`` when CRAD is absent.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine

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


@dataclass
class _ProposalAcc:
    case_id: int
    customer_id: int | None
    distributor_id: int | None
    purchase_order_id: int
    confidence: ConfidenceTier
    reason: str
    date_source: DateSource
    products: dict[int, _ProductMatch] = field(default_factory=dict)

    def proposal_key(self) -> str:
        return f"{self.case_id}:{self.customer_id or 0}:{self.distributor_id or 0}:{self.purchase_order_id}"


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
) -> dict[str, Any]:
    """Build auto-link proposals (read-only; does not write ``commercial_lineup_case_po``)."""
    try:
        return await _po_auto_link_proposals_inner(
            db,
            period=period,
            customer_id=customer_id,
            confidence=confidence,
            limit=limit,
        )
    except Exception:
        logger.exception("po-auto-link proposals failed")
        return {"proposals": [], "total": 0, "data_unavailable": True}


async def _po_auto_link_proposals_inner(
    db: AsyncSession,
    *,
    period: str | None,
    customer_id: int | None,
    confidence: ConfidenceTier | None,
    limit: int,
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
        return {"proposals": [], "total": 0, "data_unavailable": False}

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
        await db.execute(
            select(CommercialLineupCasePo.case_id, CommercialLineupCasePo.purchase_order_id).where(
                CommercialLineupCasePo.case_id.in_(case_ids)
            )
        )
    ).all():
        linked_pairs.add((int(case_id), int(po_id)))

    shipment_rows = (
        await db.execute(
            select(ShipmentEvidenceLine).where(
                ShipmentEvidenceLine.purchase_order_id.isnot(None),
                ShipmentEvidenceLine.product_id.isnot(None),
            )
        )
    ).scalars().all()

    # Lineup index: case_id -> list of lines
    lineup_by_case: dict[int, list[CommercialLineupLine]] = defaultdict(list)
    planned_by_case_product: dict[tuple[int, int], float] = defaultdict(float)
    for ln in lineup_rows:
        cid = int(ln.case_id)
        pid = int(ln.product_id)  # type: ignore[arg-type]
        lineup_by_case[cid].append(ln)
        planned_by_case_product[(cid, pid)] += float(ln.quantity_units or 0)

    proposals_map: dict[str, _ProposalAcc] = {}

    for ship in shipment_rows:
        po_id = int(ship.purchase_order_id)  # type: ignore[arg-type]
        product_id = int(ship.product_id)  # type: ignore[arg-type]
        ship_cust = int(ship.resolved_customer_id) if ship.resolved_customer_id is not None else None
        ship_dist = int(ship.resolved_distributor_id) if ship.resolved_distributor_id is not None else None
        ship_qty = float(ship.quantity or 0)
        ev_date, date_src = evidence_date_for_period_match(
            crad_date=ship.crad_date,
            schedule_ship_date=ship.schedule_ship_date,
            ship_confirm_date=ship.ship_confirm_date,
        )

        for case_id, case_lines in lineup_by_case.items():
            if (case_id, po_id) in linked_pairs:
                continue
            case = case_by_id[case_id]
            period_start = case.inferred_period_start
            in_period = date_in_case_period(ev_date, period_start)
            if not in_period:
                continue

            for ln in case_lines:
                if int(ln.product_id) != product_id:  # type: ignore[arg-type]
                    continue
                lineup_cust = int(ln.customer_id) if ln.customer_id is not None else None
                cust_align = classify_customer_alignment(ship_cust, lineup_cust)
                conf, reason = classify_match_confidence(
                    customer_align=cust_align,
                    date_source=date_src,
                    in_period=True,
                )
                if conf is None or reason is None:
                    continue

                prop_cust = ship_cust if ship_cust is not None else lineup_cust
                if customer_id is not None and prop_cust is not None and int(prop_cust) != int(customer_id):
                    continue
                if confidence is not None and conf != confidence:
                    continue

                lineup_dist = int(ln.distributor_id) if ln.distributor_id is not None else None
                dist_id = ship_dist if ship_dist is not None else lineup_dist

                acc = _ProposalAcc(
                    case_id=case_id,
                    customer_id=prop_cust,
                    distributor_id=dist_id,
                    purchase_order_id=po_id,
                    confidence=conf,
                    reason=reason,
                    date_source=date_src,
                )
                key = acc.proposal_key()
                existing = proposals_map.get(key)
                if existing is None:
                    proposals_map[key] = acc
                    existing = acc
                elif existing.confidence == "medium" and conf == "high":
                    existing.confidence = conf
                    existing.reason = reason
                    existing.date_source = date_src

                pm = existing.products.setdefault(product_id, _ProductMatch(product_id=product_id))
                pm.shipped_units += ship_qty
                pm.planned_units = planned_by_case_product.get((case_id, product_id), 0.0)

    po_ids = sorted({p.purchase_order_id for p in proposals_map.values()})
    po_meta: dict[int, PurchaseOrder] = {}
    if po_ids:
        for po in (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids)))).scalars().all():
            po_meta[int(po.id)] = po

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
                "already_linked": (acc.case_id, acc.purchase_order_id) in linked_pairs,
                "matched_products": [
                    {
                        "product_id": m.product_id,
                        "planned_units": round(m.planned_units, 4),
                        "shipped_units": round(m.shipped_units, 4),
                    }
                    for m in products
                ],
                "total_planned_units": round(sum(m.planned_units for m in products), 4),
                "total_shipped_units": round(sum(m.shipped_units for m in products), 4),
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
    }
