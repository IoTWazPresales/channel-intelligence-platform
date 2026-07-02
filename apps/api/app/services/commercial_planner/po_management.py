"""PO Management surface (Session C Unit 3). Derived on read; nothing stored.

Groups observed purchase orders (materialized from shipment evidence) by quarter/year then inferred
product line (shipment ``product_id`` -> ``dim_product.product_line``/``business_unit``). Coverage
reports POs observed vs linked to a confirmed lineup case. Backlog splits groups into linked
(with a reconciliation summary) and unlinked (with an upload prompt to pre-fill the import wizard).
Shipped value is FX-bridged to the plan currency where a SKU assumption exists; otherwise the group
is marked ``fx_partial`` and value is reported best-effort.
"""
from __future__ import annotations

import logging
from typing import Any

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.dimensions import DimProduct
from app.models.facts import FactInboundShipment
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    case_coverage_key,
    quarter_key_from_period_start,
)
from app.services.commercial_planner.lineup_po_reconciliation import UNITS_FLAGS, reconcile_case

logger = logging.getLogger(__name__)

# Read-model contract: shipped quantities on PO Management come from the truth layer only.
SHIPMENT_QUANTITY_SOURCE = "fact_inbound_shipment"


def _quarter_label(year: int, q: int) -> str:
    if year == 0:
        return "Undated"
    start_month = 3 * (q - 1) + 1
    return quarter_key_from_period_start(date(year, start_month, 1))


async def _observed_groups(db: AsyncSession) -> dict[tuple[int, int, str], dict[str, Any]]:
    """Group observed POs by (year, quarter, product_line). One PO can span several groups."""
    rep_date = func.coalesce(
        FactInboundShipment.ship_confirm_date,
        FactInboundShipment.schedule_ship_date,
        FactInboundShipment.crad_date,
    )
    shipped_qty = case(
        (FactInboundShipment.line_state == "shipped", FactInboundShipment.quantity),
        else_=0,
    )
    shipped_value = case(
        (
            FactInboundShipment.line_state == "shipped",
            func.coalesce(
                FactInboundShipment.amount,
                func.coalesce(FactInboundShipment.quantity, 0) * func.coalesce(FactInboundShipment.unit_price, 0),
            ),
        ),
        else_=0,
    )
    rows = (
        await db.execute(
            select(
                FactInboundShipment.purchase_order_id,
                FactInboundShipment.product_id,
                func.coalesce(func.sum(shipped_qty), 0),
                func.coalesce(func.sum(shipped_value), 0),
                func.max(rep_date),
            )
            .where(
                FactInboundShipment.purchase_order_id.isnot(None),
                FactInboundShipment.product_id.isnot(None),
            )
            .group_by(FactInboundShipment.purchase_order_id, FactInboundShipment.product_id)
        )
    ).all()

    product_ids = sorted({int(p) for _po, p, _u, _v, _r in rows if p is not None})
    pline_by_product: dict[int, str] = {}
    fx_by_product: dict[int, float] = {}
    if product_ids:
        for pid, pline, bu in (
            await db.execute(
                select(DimProduct.id, DimProduct.product_line, DimProduct.business_unit)
                .where(DimProduct.id.in_(product_ids))
            )
        ).all():
            pline_by_product[int(pid)] = (pline or bu or "Unclassified")
        for pid, fx in (
            await db.execute(
                select(CommercialSkuAssumption.product_id, CommercialSkuAssumption.fx_plan_currency_per_cost_currency)
                .where(CommercialSkuAssumption.product_id.in_(product_ids))
            )
        ).all():
            if fx is not None:
                fx_by_product[int(pid)] = float(fx)

    groups: dict[tuple[int, int, str], dict[str, Any]] = {}
    for po, pid, units, value_cost, rep in rows:
        if po is None:
            continue
        pid_int = int(pid) if pid is not None else None
        pline = pline_by_product.get(pid_int, "Unclassified") if pid_int is not None else "Unclassified"
        if rep is not None:
            q = (rep.month - 1) // 3 + 1
            year = rep.year
        else:
            q, year = 0, 0
        key = (year, q, pline)
        g = groups.setdefault(
            key,
            {
                "year": year,
                "quarter": q,
                "quarter_label": _quarter_label(year, q),
                "product_line": pline,
                "po_ids": set(),
                "shipped_units": 0.0,
                "shipped_value_cost": 0.0,
                "shipped_value_plan": 0.0,
                "fx_complete": True,
            },
        )
        g["po_ids"].add(int(po))
        g["shipped_units"] += float(units)
        g["shipped_value_cost"] += float(value_cost)
        fx = fx_by_product.get(pid_int) if pid_int is not None else None
        if fx is None:
            g["fx_complete"] = False
        else:
            g["shipped_value_plan"] += float(value_cost) * fx
    return groups


async def _active_lineup_coverage_keys(db: AsyncSession) -> set[tuple[int, int, str]]:
    """(year, quarter, product_line) slices with at least one active lineup case."""
    rows = (
        await db.execute(
            select(CommercialLineupCase).where(
                CommercialLineupCase.inferred_period_start.isnot(None),
                *active_lineup_case_filters(),
            )
        )
    ).scalars().all()
    keys: set[tuple[int, int, str]] = set()
    for case in rows:
        keys |= case_coverage_key(case)
    return keys


async def _linked_po_ids(db: AsyncSession) -> set[int]:
    rows = (
        await db.execute(
            select(CommercialLineupCasePo.purchase_order_id)
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
            .where(*active_lineup_case_filters())
            .distinct()
        )
    ).scalars().all()
    return {int(x) for x in rows if x is not None}


async def coverage(db: AsyncSession) -> dict[str, Any]:
    try:
        groups = await _observed_groups(db)
        linked = await _linked_po_ids(db)
    except Exception:
        logger.exception("po-management coverage failed")
        return {"total_pos_observed": 0, "total_pos_linked": 0, "first_run": True, "groups": [], "data_unavailable": True}

    all_po_ids: set[int] = set()
    out_groups: list[dict[str, Any]] = []
    for g in groups.values():
        po_ids = g.pop("po_ids")
        all_po_ids |= po_ids
        out_groups.append(
            {
                **g,
                "po_count": len(po_ids),
                "linked_po_count": len(po_ids & linked),
            }
        )
    out_groups.sort(key=lambda x: (x["year"], x["quarter"], x["product_line"]), reverse=True)
    return {
        "total_pos_observed": len(all_po_ids),
        "total_pos_linked": len(all_po_ids & linked),
        "first_run": len(all_po_ids & linked) == 0,
        "groups": out_groups,
        "data_unavailable": False,
    }


async def backlog(db: AsyncSession) -> dict[str, Any]:
    try:
        groups = await _observed_groups(db)
        linked = await _linked_po_ids(db)
        lineup_coverage = await _active_lineup_coverage_keys(db)
        # PO -> linked active case ids (for reconciliation rollup on linked groups).
        case_links = (
            await db.execute(
                select(CommercialLineupCasePo.purchase_order_id, CommercialLineupCasePo.case_id)
                .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
                .where(*active_lineup_case_filters())
            )
        ).all()
    except Exception:
        logger.exception("po-management backlog failed")
        return {"groups": [], "data_unavailable": True}

    po_to_cases: dict[int, set[int]] = {}
    for po, case_id in case_links:
        po_to_cases.setdefault(int(po), set()).add(int(case_id))

    out_groups: list[dict[str, Any]] = []
    for g in groups.values():
        po_ids: set[int] = g.pop("po_ids")
        linked_pos = po_ids & linked
        is_linked = bool(linked_pos)
        entry: dict[str, Any] = {
            **g,
            "po_count": len(po_ids),
            "linked_po_count": len(linked_pos),
            "status": "linked" if is_linked else "unlinked",
        }
        if is_linked:
            case_ids: set[int] = set()
            for po in linked_pos:
                case_ids |= po_to_cases.get(po, set())
            summary = {f: 0 for f in UNITS_FLAGS}
            for cid in case_ids:
                try:
                    recon = await reconcile_case(db, cid)
                except Exception:
                    logger.exception("backlog reconcile_case failed cid=%s", cid)
                    continue
                for f in UNITS_FLAGS:
                    summary[f] += recon.get("summary", {}).get(f, 0)
            entry["reconciliation_summary"] = summary
            entry["linked_case_ids"] = sorted(case_ids)
        else:
            coverage_key = (int(g["year"]), int(g["quarter"]), str(g["product_line"]))
            if coverage_key in lineup_coverage:
                entry["lineup_case_exists"] = True
            else:
                entry["upload_prompt"] = {
                    "period_label": g["quarter_label"] if g["year"] else None,
                    "product_line": g["product_line"],
                }
        out_groups.append(entry)

    out_groups.sort(key=lambda x: (x["year"], x["quarter"], x["product_line"]), reverse=True)
    return {"groups": out_groups, "data_unavailable": False}
