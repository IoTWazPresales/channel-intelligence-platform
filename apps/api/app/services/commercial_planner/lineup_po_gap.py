"""PO gap worklist (Session C Unit 3). Derived on read; nothing stored.

A (PO, product) shipment grain is a *gap* when its ``purchase_order_id`` is not linked through
``commercial_lineup_case_po`` to a case whose lineup contains that ``product_id`` — i.e. stock is
arriving under a PO that no confirmed lineup covers. Rows are grouped by quarter/year derived from
``ship_confirm_date`` (fallback ``schedule_ship_date``). Dismissal reuses the PO-level
``purchase_order.dismiss_reason_code`` (mirrors the DSI ignore pattern).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimProduct
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_period_canonical import active_lineup_case_filters

logger = logging.getLogger(__name__)

# Read-model contract: gap shipped quantities come from the truth layer only.
SHIPMENT_QUANTITY_SOURCE = "fact_inbound_shipment"


def _quarter(year: int, month: int) -> tuple[int, int, str]:
    q = (month - 1) // 3 + 1
    return year, q, f"{str(year)[-2:]}Q{q}"


class PurchaseOrderNotFoundError(Exception):
    pass


async def po_gap_worklist(db: AsyncSession, *, include_dismissed: bool = False) -> dict[str, Any]:
    try:
        return await _po_gap_worklist_inner(db, include_dismissed=include_dismissed)
    except Exception:
        logger.exception("po-gap-worklist failed")
        return {"groups": [], "dismissed": [], "total_gap_rows": 0, "data_unavailable": True}


async def _po_gap_worklist_inner(db: AsyncSession, *, include_dismissed: bool) -> dict[str, Any]:
    # Covered (po, product) pairs: PO linked to a case whose lineup contains that product.
    covered_rows = (
        await db.execute(
            select(CommercialLineupCasePo.purchase_order_id, CommercialLineupLine.product_id)
            .join(CommercialLineupLine, CommercialLineupLine.case_id == CommercialLineupCasePo.case_id)
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
            .where(
                CommercialLineupLine.product_id.isnot(None),
                CommercialLineupLine.row_status != "superseded",
                *active_lineup_case_filters(),
            )
            .distinct()
        )
    ).all()
    covered: set[tuple[int, int]] = {(int(po), int(pid)) for po, pid in covered_rows}

    # Dismissed POs (PO-level reuse of dismiss_reason_code).
    dismissed_rows = (
        await db.execute(
            select(PurchaseOrder.id, PurchaseOrder.po_number_raw, PurchaseOrder.dismiss_reason_code)
            .where(PurchaseOrder.dismiss_reason_code.isnot(None))
        )
    ).all()
    dismissed_ids = {int(r[0]) for r in dismissed_rows}

    # Shipment (po, product) aggregates with a representative quarter date (shipped lines only).
    rep_date = func.coalesce(
        FactInboundShipment.ship_confirm_date,
        FactInboundShipment.schedule_ship_date,
        FactInboundShipment.crad_date,
    )
    shipped_qty = case(
        (FactInboundShipment.line_state == "shipped", FactInboundShipment.quantity),
        else_=0,
    )
    ship_rows = (
        await db.execute(
            select(
                FactInboundShipment.purchase_order_id,
                FactInboundShipment.product_id,
                func.coalesce(func.sum(shipped_qty), 0),
                func.max(rep_date),
            )
            .where(
                FactInboundShipment.purchase_order_id.isnot(None),
                FactInboundShipment.product_id.isnot(None),
            )
            .group_by(FactInboundShipment.purchase_order_id, FactInboundShipment.product_id)
        )
    ).all()

    gap_pairs = [
        (int(po), int(pid), float(units), rep)
        for po, pid, units, rep in ship_rows
        if (int(po), int(pid)) not in covered and float(units) > 0
    ]

    # Metadata for PO numbers + product names/lines.
    po_ids = sorted({po for po, _pid, _u, _r in gap_pairs} | dismissed_ids)
    product_ids = sorted({pid for _po, pid, _u, _r in gap_pairs})
    po_meta: dict[int, str | None] = {}
    if po_ids:
        for pid_, raw in (
            await db.execute(select(PurchaseOrder.id, PurchaseOrder.po_number_raw).where(PurchaseOrder.id.in_(po_ids)))
        ).all():
            po_meta[int(pid_)] = raw
    prod_meta: dict[int, dict[str, Any]] = {}
    if product_ids:
        for pid_, name, pline, bu in (
            await db.execute(
                select(DimProduct.id, DimProduct.name, DimProduct.product_line, DimProduct.business_unit)
                .where(DimProduct.id.in_(product_ids))
            )
        ).all():
            prod_meta[int(pid_)] = {
                "product_name": name,
                "product_line": pline or bu,
            }

    groups: dict[tuple[int, int], dict[str, Any]] = {}
    total = 0
    for po, pid, units, rep in gap_pairs:
        if po in dismissed_ids and not include_dismissed:
            continue
        if rep is not None:
            year, q, label = _quarter(rep.year, rep.month)
        else:
            year, q, label = 0, 0, "Undated"
        key = (year, q)
        g = groups.setdefault(
            key,
            {
                "year": year,
                "quarter": q,
                "quarter_label": label,
                "rows": [],
                "shipped_units": 0.0,
            },
        )
        pm = prod_meta.get(pid, {})
        g["rows"].append(
            {
                "purchase_order_id": po,
                "po_number_raw": po_meta.get(po),
                "product_id": pid,
                "product_name": pm.get("product_name"),
                "product_line": pm.get("product_line"),
                "shipped_units": units,
                "period_label": label,
                "dismissed": po in dismissed_ids,
            }
        )
        g["shipped_units"] += units
        total += 1

    group_list = sorted(groups.values(), key=lambda g: (g["year"], g["quarter"]), reverse=True)
    for g in group_list:
        g["po_count"] = len({r["purchase_order_id"] for r in g["rows"]})
        g["product_count"] = len({r["product_id"] for r in g["rows"]})

    dismissed = [
        {"purchase_order_id": int(r[0]), "po_number_raw": r[1], "dismiss_reason_code": r[2]}
        for r in dismissed_rows
    ]

    return {
        "groups": group_list,
        "dismissed": dismissed,
        "total_gap_rows": total,
        "data_unavailable": False,
    }


async def dismiss_gap_po(db: AsyncSession, purchase_order_id: int, reason_code: str) -> dict[str, Any]:
    po = await db.get(PurchaseOrder, purchase_order_id)
    if po is None:
        raise PurchaseOrderNotFoundError(str(purchase_order_id))
    po.dismiss_reason_code = (reason_code or "").strip() or "dismissed"
    await db.commit()
    return {"purchase_order_id": purchase_order_id, "dismiss_reason_code": po.dismiss_reason_code}


async def restore_gap_po(db: AsyncSession, purchase_order_id: int) -> dict[str, Any]:
    po = await db.get(PurchaseOrder, purchase_order_id)
    if po is None:
        raise PurchaseOrderNotFoundError(str(purchase_order_id))
    po.dismiss_reason_code = None
    await db.commit()
    return {"purchase_order_id": purchase_order_id, "dismiss_reason_code": None}
