"""Lineup <-> PO reconciliation (Session C Unit 3). Derived on read; nothing stored.

Per (case x product) we aggregate every ``shipment_evidence_line`` whose ``purchase_order_id`` is
one of the case's confirmed POs and whose ``product_id`` matches a lineup line, then classify a
PRIMARY units flag. A SECONDARY value figure is bridged to the plan currency via
``commercial_sku_assumption.fx_plan_currency_per_cost_currency`` for display only — it never gates a
flag, and a missing FX is reported as ``fx_unavailable`` rather than raising.

Units flags (primary):
  matched   shipped == planned
  short     0 < shipped < planned
  over      shipped > planned
  unshipped planned > 0, shipped == 0 (PO confirmed, nothing shipped yet)
  unplanned planned == 0, shipped > 0, product line differs from the case (out of scope)
  amended   planned == 0, shipped > 0, same product line as the case (distributor amendment, review)
  po_no_match  a confirmed case PO with zero shipment lines anywhere (PO-level flag)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.dimensions import DimProduct
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)

EV = shipment_evidence_read_model()

logger = logging.getLogger(__name__)

_EACHES_UNITS = {"", "ea", "each", "eaches", "unit", "units", "pc", "pcs", "piece", "pieces", "qty"}

UNITS_FLAGS = ("matched", "short", "over", "unshipped", "unplanned", "amended", "po_no_match")


class CaseNotFoundError(Exception):
    pass


def _classify_units(planned: float, shipped: float) -> str | None:
    """Flag for an in-lineup product. Returns None for the planned==0 case (handled by caller)."""
    if planned > 0 and shipped == 0:
        return "unshipped"
    if planned > 0 and shipped == planned:
        return "matched"
    if planned > 0 and shipped < planned:
        return "short"
    if planned > 0 and shipped > planned:
        return "over"
    return None


def _same_product_line(case_line: str | None, product_line: str | None, business_unit: str | None) -> bool:
    if not case_line:
        return False
    target = case_line.strip().lower()
    for candidate in (product_line, business_unit):
        if candidate and candidate.strip().lower() == target:
            return True
    return False


async def reconcile_case(db: AsyncSession, case_id: int) -> dict[str, Any]:
    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise CaseNotFoundError(str(case_id))

    try:
        return await _reconcile_case_inner(db, case)
    except CaseNotFoundError:
        raise
    except Exception:  # optional-table / query failure -> graceful empty state, not 500
        logger.exception("po-reconciliation failed for case_id=%s", case_id)
        return {
            "case_id": case_id,
            "commercial_status": case.commercial_status,
            "plan_currency": case.currency_code,
            "linked_po_count": 0,
            "products": [],
            "po_flags": [],
            "summary": {f: 0 for f in UNITS_FLAGS},
            "data_unavailable": True,
        }


async def _reconcile_case_inner(db: AsyncSession, case: CommercialLineupCase) -> dict[str, Any]:
    case_id = int(case.id)

    # Linked POs for this case
    po_rows = (
        await db.execute(
            select(PurchaseOrder.id, PurchaseOrder.po_number_raw, PurchaseOrder.po_number_norm)
            .join(CommercialLineupCasePo, CommercialLineupCasePo.purchase_order_id == PurchaseOrder.id)
            .where(CommercialLineupCasePo.case_id == case_id)
        )
    ).all()
    po_ids = [int(r[0]) for r in po_rows]
    po_label = {int(r[0]): (r[1] or r[2]) for r in po_rows}

    # Planned units + planned DAP value (plan currency) per product, from lineup lines.
    planned_rows = (
        await db.execute(
            select(
                CommercialLineupLine.product_id,
                func.coalesce(func.sum(CommercialLineupLine.quantity_units), 0),
                func.coalesce(
                    func.sum(
                        CommercialLineupLine.quantity_units
                        * func.coalesce(CommercialLineupLine.dap_evidence_local, 0)
                    ),
                    0,
                ),
            )
            .where(CommercialLineupLine.case_id == case_id, CommercialLineupLine.product_id.isnot(None))
            .group_by(CommercialLineupLine.product_id)
        )
    ).all()
    planned: dict[int, dict[str, float]] = {
        int(pid): {"units": float(units), "value_plan": float(val)}
        for pid, units, val in planned_rows
    }

    # Distinct lineup units-of-measure per product (for the eaches assertion / warning).
    uom_rows = (
        await db.execute(
            select(CommercialLineupLine.product_id, CommercialLineupLine.base_unit_raw)
            .where(CommercialLineupLine.case_id == case_id, CommercialLineupLine.product_id.isnot(None))
            .distinct()
        )
    ).all()
    uom_by_product: dict[int, set[str]] = {}
    for pid, unit in uom_rows:
        uom_by_product.setdefault(int(pid), set()).add((unit or "").strip())

    # Shipped units + shipped value (cost currency) per product under the case POs.
    shipped: dict[int, dict[str, float]] = {}
    if po_ids:
        shipped_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(
                        EV.product_id,
                        func.coalesce(func.sum(EV.quantity), 0),
                        func.coalesce(
                            func.sum(
                                func.coalesce(
                                    EV.amount,
                                    func.coalesce(EV.quantity, 0)
                                    * func.coalesce(EV.unit_price, 0),
                                )
                            ),
                            0,
                        ),
                    )
                    .where(
                        EV.purchase_order_id.in_(po_ids),
                        EV.product_id.isnot(None),
                    )
                    .group_by(EV.product_id),
                    model=EV,
                )
            )
        ).all()
        shipped = {
            int(pid): {"units": float(units), "value_cost": float(val)}
            for pid, units, val in shipped_rows
        }

    # po_no_match: confirmed case POs with zero shipment lines anywhere.
    po_with_shipments: set[int] = set()
    if po_ids:
        rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(EV.purchase_order_id)
                    .where(EV.purchase_order_id.in_(po_ids))
                    .distinct(),
                    model=EV,
                )
            )
        ).scalars().all()
        po_with_shipments = {int(x) for x in rows if x is not None}
    po_flags = [
        {"purchase_order_id": pid, "po_number_raw": po_label.get(pid), "flag": "po_no_match"}
        for pid in po_ids
        if pid not in po_with_shipments
    ]

    # Product metadata + FX for every product we touch.
    product_ids = sorted(set(planned) | set(shipped))
    meta: dict[int, dict[str, Any]] = {}
    fx_by_product: dict[int, float] = {}
    if product_ids:
        for pid, name, pline, bu in (
            await db.execute(
                select(DimProduct.id, DimProduct.name, DimProduct.product_line, DimProduct.business_unit)
                .where(DimProduct.id.in_(product_ids))
            )
        ).all():
            meta[int(pid)] = {"product_name": name, "product_line": pline, "business_unit": bu}
        for pid, fx in (
            await db.execute(
                select(CommercialSkuAssumption.product_id, CommercialSkuAssumption.fx_plan_currency_per_cost_currency)
                .where(CommercialSkuAssumption.product_id.in_(product_ids))
            )
        ).all():
            if fx is not None:
                fx_by_product[int(pid)] = float(fx)

    products: list[dict[str, Any]] = []
    summary = {f: 0 for f in UNITS_FLAGS}

    for pid in product_ids:
        planned_units = planned.get(pid, {}).get("units", 0.0)
        planned_value_plan = planned.get(pid, {}).get("value_plan", 0.0)
        shipped_units = shipped.get(pid, {}).get("units", 0.0)
        shipped_value_cost = shipped.get(pid, {}).get("value_cost", 0.0)
        pmeta = meta.get(pid, {})

        flag = _classify_units(planned_units, shipped_units)
        if flag is None:
            # planned == 0, shipped > 0 -> distributor extra under a case PO
            if _same_product_line(case.product_line, pmeta.get("product_line"), pmeta.get("business_unit")):
                flag = "amended"
            else:
                flag = "unplanned"
        summary[flag] += 1

        # Value (secondary, display only): bridge shipped cost-ccy to plan ccy.
        fx = fx_by_product.get(pid)
        if fx is None:
            value_status = "fx_unavailable"
            shipped_value_plan = None
            variance_plan = None
        else:
            value_status = "ok"
            shipped_value_plan = shipped_value_cost * fx
            variance_plan = shipped_value_plan - planned_value_plan

        # UoM assertion: lineup units should be eaches to compare against shipment quantity.
        warnings: list[str] = []
        non_each = {u for u in uom_by_product.get(pid, set()) if u.lower() not in _EACHES_UNITS}
        if non_each:
            msg = (
                f"UoM mismatch risk: lineup base unit(s) {sorted(non_each)} for product {pid} "
                "are not 'eaches'; shipment quantity is summed as eaches."
            )
            warnings.append(msg)
            logger.warning("po-reconciliation case=%s %s", case_id, msg)

        products.append(
            {
                "product_id": pid,
                "product_name": pmeta.get("product_name"),
                "product_line": pmeta.get("product_line"),
                "planned_units": planned_units,
                "shipped_units": shipped_units,
                "units_flag": flag,
                "value": {
                    "planned_value_plan": planned_value_plan,
                    "shipped_value_cost": shipped_value_cost,
                    "shipped_value_plan": shipped_value_plan,
                    "variance_plan": variance_plan,
                    "fx_plan_per_cost": fx,
                    "value_status": value_status,
                },
                "warnings": warnings,
            }
        )

    summary["po_no_match"] = len(po_flags)

    return {
        "case_id": case_id,
        "commercial_status": case.commercial_status,
        "plan_currency": case.currency_code,
        "linked_po_count": len(po_ids),
        "products": products,
        "po_flags": po_flags,
        "summary": summary,
        "data_unavailable": False,
    }
