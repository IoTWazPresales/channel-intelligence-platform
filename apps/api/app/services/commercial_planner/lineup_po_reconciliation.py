"""Lineup <-> PO reconciliation (Session C Unit 3). Derived on read; nothing stored.

Per (case x customer x product) we aggregate planned lineup lines and shipment evidence on
confirmed case POs, then roll up to customer slices and case summary. Customer-grain
reconciliation avoids staggered per-customer PO confirmation reading as case-wide ``short``.

Units flags (primary):
  matched   shipped == planned
  short     0 < shipped < planned
  over      shipped > planned
  unshipped planned > 0, shipped == 0 (PO linked, nothing shipped yet for this customer/product)
  unplanned planned == 0, shipped > 0, product line differs from the case
  amended   planned == 0, shipped > 0, same product line as the case
  po_no_match  a confirmed case PO with zero shipment lines anywhere (PO-level flag)

Customer slice flag (not in UNITS_FLAGS rollup):
  awaiting_po  customer has planned lines but no linked-PO shipment resolves to that customer
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
from app.models.dimensions import DimCustomer, DimProduct
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)

EV = shipment_evidence_read_model()

logger = logging.getLogger(__name__)

_EACHES_UNITS = {"", "ea", "each", "eaches", "unit", "units", "pc", "pcs", "piece", "pieces", "qty"}

UNITS_FLAGS = ("matched", "short", "over", "unshipped", "unplanned", "amended", "po_no_match")

UNATTRIBUTED_CUSTOMER_KEY = "__unattributed__"


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


def _customer_label(customer_id: int | None, names: dict[int, str]) -> str:
    if customer_id is None:
        return "Unattributed"
    return names.get(int(customer_id)) or f"Customer #{customer_id}"


def _rollup_summary(slices: list[dict[str, Any]]) -> dict[str, int]:
    summary = {f: 0 for f in UNITS_FLAGS}
    for sl in slices:
        for f in UNITS_FLAGS:
            summary[f] += int(sl.get("summary", {}).get(f, 0))
    return summary


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
            "customers": [],
            "po_flags": [],
            "summary": {f: 0 for f in UNITS_FLAGS},
            "data_unavailable": True,
        }


async def _reconcile_case_inner(db: AsyncSession, case: CommercialLineupCase) -> dict[str, Any]:
    case_id = int(case.id)

    po_rows = (
        await db.execute(
            select(PurchaseOrder.id, PurchaseOrder.po_number_raw, PurchaseOrder.po_number_norm)
            .join(CommercialLineupCasePo, CommercialLineupCasePo.purchase_order_id == PurchaseOrder.id)
            .where(CommercialLineupCasePo.case_id == case_id)
        )
    ).all()
    po_ids = [int(r[0]) for r in po_rows]
    po_label = {int(r[0]): (r[1] or r[2]) for r in po_rows}

    planned_rows = (
        await db.execute(
            select(
                CommercialLineupLine.customer_id,
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
            .group_by(CommercialLineupLine.customer_id, CommercialLineupLine.product_id)
        )
    ).all()
    planned: dict[tuple[int | None, int], dict[str, float]] = {}
    for cust_id, pid, units, val in planned_rows:
        planned[(int(cust_id) if cust_id is not None else None, int(pid))] = {
            "units": float(units),
            "value_plan": float(val),
        }

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

    shipped: dict[tuple[int | None, int], dict[str, float]] = {}
    resolved_customers_on_pos: set[int] = set()
    if po_ids:
        shipped_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(
                        EV.resolved_customer_id,
                        EV.product_id,
                        func.coalesce(func.sum(EV.quantity), 0),
                        func.coalesce(
                            func.sum(
                                func.coalesce(
                                    EV.amount,
                                    func.coalesce(EV.quantity, 0) * func.coalesce(EV.unit_price, 0),
                                )
                            ),
                            0,
                        ),
                    )
                    .where(
                        EV.purchase_order_id.in_(po_ids),
                        EV.product_id.isnot(None),
                    )
                    .group_by(EV.resolved_customer_id, EV.product_id),
                    model=EV,
                )
            )
        ).all()
        for cust_id, pid, units, val in shipped_rows:
            key = (int(cust_id) if cust_id is not None else None, int(pid))
            shipped[key] = {"units": float(units), "value_cost": float(val)}

        resolved_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(EV.resolved_customer_id)
                    .where(
                        EV.purchase_order_id.in_(po_ids),
                        EV.resolved_customer_id.isnot(None),
                    )
                    .distinct(),
                    model=EV,
                )
            )
        ).scalars().all()
        resolved_customers_on_pos = {int(x) for x in resolved_rows if x is not None}

    po_with_shipments: set[int] = set()
    if po_ids:
        rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(EV.purchase_order_id).where(EV.purchase_order_id.in_(po_ids)).distinct(),
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

    product_ids = sorted({pid for _c, pid in set(planned) | set(shipped)})
    customer_ids = sorted({c for c, _p in set(planned) | set(shipped) if c is not None})

    meta: dict[int, dict[str, Any]] = {}
    fx_by_product: dict[int, float] = {}
    customer_names: dict[int, str] = {}
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
    if customer_ids:
        for cid, name in (
            await db.execute(select(DimCustomer.id, DimCustomer.name).where(DimCustomer.id.in_(customer_ids)))
        ).all():
            customer_names[int(cid)] = str(name)

    cust_keys: set[int | None] = {c for c, _ in planned} | {c for c, _ in shipped}
    if not cust_keys and planned_rows:
        cust_keys.add(None)

    customers_out: list[dict[str, Any]] = []
    products_flat: list[dict[str, Any]] = []

    for cust_id in sorted(cust_keys, key=lambda c: (c is None, c or 0)):
        awaiting_po = (
            cust_id is not None
            and bool(po_ids)
            and any(planned.get((cust_id, pid), {}).get("units", 0) > 0 for pid in product_ids)
            and cust_id not in resolved_customers_on_pos
        )
        slice_pids = sorted(
            {
                pid
                for (c, pid) in set(planned) | set(shipped)
                if c == cust_id
                and (
                    planned.get((c, pid), {}).get("units", 0) > 0
                    or shipped.get((c, pid), {}).get("units", 0) > 0
                )
            }
        )
        slice_products: list[dict[str, Any]] = []
        slice_summary = {f: 0 for f in UNITS_FLAGS}

        for pid in slice_pids:
            planned_units = planned.get((cust_id, pid), {}).get("units", 0.0)
            planned_value_plan = planned.get((cust_id, pid), {}).get("value_plan", 0.0)
            shipped_units = shipped.get((cust_id, pid), {}).get("units", 0.0)
            shipped_value_cost = shipped.get((cust_id, pid), {}).get("value_cost", 0.0)
            pmeta = meta.get(pid, {})

            if awaiting_po and planned_units > 0:
                flag = None
            else:
                flag = _classify_units(planned_units, shipped_units)
                if flag is None:
                    if shipped_units > 0:
                        if _same_product_line(
                            case.product_line, pmeta.get("product_line"), pmeta.get("business_unit")
                        ):
                            flag = "amended"
                        else:
                            flag = "unplanned"
                if flag is not None:
                    slice_summary[flag] += 1

            fx = fx_by_product.get(pid)
            if fx is None:
                value_status = "fx_unavailable"
                shipped_value_plan = None
                variance_plan = None
            else:
                value_status = "ok"
                shipped_value_plan = shipped_value_cost * fx
                variance_plan = shipped_value_plan - planned_value_plan

            warnings: list[str] = []
            non_each = {u for u in uom_by_product.get(pid, set()) if u.lower() not in _EACHES_UNITS}
            if non_each:
                warnings.append(
                    f"UoM mismatch risk: lineup base unit(s) {sorted(non_each)} for product {pid} "
                    "are not 'eaches'; shipment quantity is summed as eaches."
                )

            row = {
                "product_id": pid,
                "customer_id": cust_id,
                "product_name": pmeta.get("product_name"),
                "product_line": pmeta.get("product_line"),
                "planned_units": planned_units,
                "shipped_units": shipped_units,
                "units_flag": flag,
                "awaiting_po": awaiting_po and planned_units > 0,
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
            slice_products.append(row)
            products_flat.append(row)

        customers_out.append(
            {
                "customer_id": cust_id,
                "label": _customer_label(cust_id, customer_names),
                "awaiting_po": awaiting_po,
                "products": slice_products,
                "summary": slice_summary,
            }
        )

    summary = _rollup_summary(customers_out)
    summary["po_no_match"] = len(po_flags)

    return {
        "case_id": case_id,
        "commercial_status": case.commercial_status,
        "plan_currency": case.currency_code,
        "linked_po_count": len(po_ids),
        "products": products_flat,
        "customers": customers_out,
        "po_flags": po_flags,
        "summary": summary,
        "data_unavailable": False,
    }


def reconcile_case_legacy_product_grain_summary(
    planned: dict[int, dict[str, float]],
    shipped: dict[int, dict[str, float]],
    *,
    product_line: str | None,
    meta: dict[int, dict[str, Any]],
) -> dict[str, int]:
    """Legacy product-only rollup (for parity tests on distinct-product multi-customer fixtures)."""
    summary = {f: 0 for f in UNITS_FLAGS}
    for pid in sorted(set(planned) | set(shipped)):
        planned_units = planned.get(pid, {}).get("units", 0.0)
        shipped_units = shipped.get(pid, {}).get("units", 0.0)
        flag = _classify_units(planned_units, shipped_units)
        if flag is None and shipped_units > 0:
            pmeta = meta.get(pid, {})
            flag = (
                "amended"
                if _same_product_line(product_line, pmeta.get("product_line"), pmeta.get("business_unit"))
                else "unplanned"
            )
        if flag is not None:
            summary[flag] += 1
    return summary
