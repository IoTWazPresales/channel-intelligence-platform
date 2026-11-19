"""Lineup <-> PO reconciliation (Session C Unit 3). Derived on read; nothing stored.

Per (case x customer x product) we aggregate planned lineup lines and shipment evidence on
confirmed case POs, then roll up to customer slices and case summary. Customer-grain
reconciliation avoids staggered per-customer PO confirmation reading as case-wide ``short``.

``shipped_units`` counts SHIPPED execution only (``line_state='shipped'``). ``open_order``
evidence is aggregated separately as ``pipeline_units`` (allocated/inbound, not shipped) and
never enters shipped or fill. See docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md.

Units flags (primary; all computed off shipped-only quantity):
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
from collections.abc import Iterable
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
from app.services.commercial_planner.lineup_period_canonical import active_lineup_line_filters
from app.services.commercial_planner.lineup_open_channel import effective_lineup_customer_id
from app.services.commercial_planner.open_channel_customer import (
    canonical_open_channel_customer_id,
    get_open_channel_canonical_and_aliases,
)
from app.services.imports.shipment_evidence_read import (
    active_evidence_line_predicate,
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)
from app.services.shipment_strict_pair import twin_remainder
from app.services.imports.shipment_evidence_report_detect import (
    LINE_OPEN_ORDER,
    LINE_SHIPPED,
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


def _unavailable_payload(case: CommercialLineupCase) -> dict[str, Any]:
    return {
        "case_id": int(case.id),
        "commercial_status": case.commercial_status,
        "plan_currency": case.currency_code,
        "linked_po_count": 0,
        "products": [],
        "customers": [],
        "po_flags": [],
        "summary": {f: 0 for f in UNITS_FLAGS},
        "data_unavailable": True,
    }


async def reconcile_case(db: AsyncSession, case_id: int) -> dict[str, Any]:
    """One case: a thin wrapper over :func:`reconcile_cases`."""
    out = await reconcile_cases(db, [case_id])
    payload = out.get(int(case_id))
    if payload is None:
        raise CaseNotFoundError(str(case_id))
    return payload


async def reconcile_cases(db: AsyncSession, case_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Reconcile many cases in a fixed number of queries (independent of ``len(case_ids)``).

    Returns ``{case_id: payload}`` where each payload is exactly what the old per-case path
    produced. Unknown case ids are omitted (``reconcile_case`` raises ``CaseNotFoundError``).
    A query failure (optional table missing, etc.) gives every found case the graceful
    ``data_unavailable`` payload rather than a 500; a compute failure does so for that case only.
    """
    ids = list(dict.fromkeys(int(c) for c in case_ids))
    if not ids:
        return {}
    cases = (
        await db.execute(select(CommercialLineupCase).where(CommercialLineupCase.id.in_(ids)))
    ).scalars().all()
    by_id = {int(c.id): c for c in cases}
    ordered = [by_id[i] for i in ids if i in by_id]
    if not ordered:
        return {}

    try:
        data = await _fetch_batch(db, [int(c.id) for c in ordered])
    except Exception:  # optional-table / query failure -> graceful empty state, not 500
        logger.exception("po-reconciliation batch failed for %d case(s)", len(ordered))
        return {int(c.id): _unavailable_payload(c) for c in ordered}

    out: dict[int, dict[str, Any]] = {}
    for case in ordered:
        try:
            out[int(case.id)] = _build_case_payload(case, data)
        except Exception:
            logger.exception("po-reconciliation failed for case_id=%s", case.id)
            out[int(case.id)] = _unavailable_payload(case)
    return out


async def _reconcile_case_inner(db: AsyncSession, case: CommercialLineupCase) -> dict[str, Any]:
    """Fetch + build for an already-loaded case; errors propagate (no graceful fallback)."""
    data = await _fetch_batch(db, [int(case.id)])
    return _build_case_payload(case, data)


class _BatchData:
    """Everything the per-case builder needs, fetched for all cases at once."""

    def __init__(self) -> None:
        self.open_channel_customer_id: int | None = None
        self.open_channel_alias_ids: frozenset[int] = frozenset()
        self.po_rows: dict[int, list[tuple[int, Any, Any]]] = {}
        self.lines: dict[int, list[Any]] = {}
        self.shipped_rows: dict[int, list[tuple[Any, Any, Any, Any]]] = {}
        self.pipeline_rows: dict[int, list[tuple[Any, Any, Any]]] = {}
        self.resolved_rows: dict[int, list[Any]] = {}
        self.po_with_shipments: dict[int, set[int]] = {}
        self.meta: dict[int, dict[str, Any]] = {}
        self.fx_by_product: dict[int, float] = {}
        self.customer_names: dict[int, str] = {}


async def _fetch_batch(db: AsyncSession, case_ids: list[int]) -> _BatchData:
    d = _BatchData()
    d.open_channel_customer_id, d.open_channel_alias_ids = (
        await get_open_channel_canonical_and_aliases(db)
    )

    po_rows = (
        await db.execute(
            select(
                CommercialLineupCasePo.case_id,
                PurchaseOrder.id,
                PurchaseOrder.po_number_raw,
                PurchaseOrder.po_number_norm,
            )
            .join(
                CommercialLineupCasePo,
                CommercialLineupCasePo.purchase_order_id == PurchaseOrder.id,
            )
            .where(CommercialLineupCasePo.case_id.in_(case_ids))
            .order_by(CommercialLineupCasePo.case_id, CommercialLineupCasePo.id)
        )
    ).all()
    for case_id, po_id, raw, norm in po_rows:
        d.po_rows.setdefault(int(case_id), []).append((int(po_id), raw, norm))

    lineup_lines = (
        await db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.case_id.in_(case_ids),
                CommercialLineupLine.product_id.isnot(None),
                *active_lineup_line_filters(),
            )
        )
    ).scalars().all()
    for ln in lineup_lines:
        d.lines.setdefault(int(ln.case_id), []).append(ln)

    if po_rows:
        link_on = CommercialLineupCasePo.purchase_order_id == EV.purchase_order_id
        link_case = CommercialLineupCasePo.case_id
        link_in = link_case.in_(case_ids)
        # SHIPPED execution only (line_state='shipped'). Bitemporal read is ON so
        # apply_active_evidence_filter is a no-op — the line_state gate MUST be explicit
        # here or open_order (pipeline) inbound leaks into shipped and inflates fill rate.
        # See docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md.
        shipped_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(
                        CommercialLineupCasePo.case_id,
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
                    .select_from(EV)
                    .join(CommercialLineupCasePo, link_on)
                    .where(
                        link_in,
                        EV.product_id.isnot(None),
                        EV.line_state == LINE_SHIPPED,
                    )
                    .group_by(link_case, EV.resolved_customer_id, EV.product_id),
                    model=EV,
                )
            )
        ).all()
        for row in shipped_rows:
            d.shipped_rows.setdefault(int(row[0]), []).append(tuple(row[1:]))

        # PIPELINE (line_state='open_order'): allocated/inbound, NOT shipped. Surfaced as its
        # own forward metric; never summed into shipped or fill. An open line covered by its
        # strict shipped twins is skipped; a partly shipped one counts its remainder (D-0065).
        # Shipped totals are summed over active evidence rows only (same filter as the reads).
        # The twin CTE is a whole-table pass, so it MUST run once per batch, not once per case.
        twin = twin_remainder(EV, row_filter=active_evidence_line_predicate)
        pipeline_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(
                        CommercialLineupCasePo.case_id,
                        EV.resolved_customer_id,
                        EV.product_id,
                        func.coalesce(func.sum(twin.counted_quantity), 0),
                    )
                    .select_from(EV)
                    .join(CommercialLineupCasePo, link_on)
                    .outerjoin(twin.subquery, twin.onclause)
                    .where(
                        link_in,
                        EV.product_id.isnot(None),
                        EV.line_state == LINE_OPEN_ORDER,
                        twin.kept,
                    )
                    .group_by(link_case, EV.resolved_customer_id, EV.product_id),
                    model=EV,
                )
            )
        ).all()
        for row in pipeline_rows:
            d.pipeline_rows.setdefault(int(row[0]), []).append(tuple(row[1:]))

        resolved_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(CommercialLineupCasePo.case_id, EV.resolved_customer_id)
                    .select_from(EV)
                    .join(CommercialLineupCasePo, link_on)
                    .where(link_in, EV.resolved_customer_id.isnot(None))
                    .distinct(),
                    model=EV,
                )
            )
        ).all()
        for case_id, cust in resolved_rows:
            d.resolved_rows.setdefault(int(case_id), []).append(cust)

        shipment_po_rows = (
            await db.execute(
                apply_active_evidence_filter(
                    select(CommercialLineupCasePo.case_id, EV.purchase_order_id)
                    .select_from(EV)
                    .join(CommercialLineupCasePo, link_on)
                    .where(link_in)
                    .distinct(),
                    model=EV,
                )
            )
        ).all()
        for case_id, po_id in shipment_po_rows:
            if po_id is not None:
                d.po_with_shipments.setdefault(int(case_id), set()).add(int(po_id))

    # Product / customer lookups for every case at once (one query each).
    product_ids: set[int] = set()
    customer_ids: set[int] = set()

    def _canon(customer_id: int | None) -> int | None:
        return canonical_open_channel_customer_id(
            customer_id,
            canonical_id=d.open_channel_customer_id,
            alias_ids=d.open_channel_alias_ids,
        )

    for lines in d.lines.values():
        for ln in lines:
            product_ids.add(int(ln.product_id))
            c = _canon(
                effective_lineup_customer_id(ln, open_channel_customer_id=d.open_channel_customer_id)
            )
            if c is not None:
                customer_ids.add(c)
    for rows in d.shipped_rows.values():
        for cust_id, pid, _u, _v in rows:
            product_ids.add(int(pid))
            c = _canon(int(cust_id) if cust_id is not None else None)
            if c is not None:
                customer_ids.add(c)

    if product_ids:
        for pid, name, pline, bu in (
            await db.execute(
                select(
                    DimProduct.id, DimProduct.name, DimProduct.product_line, DimProduct.business_unit
                ).where(DimProduct.id.in_(sorted(product_ids)))
            )
        ).all():
            d.meta[int(pid)] = {"product_name": name, "product_line": pline, "business_unit": bu}
        for pid, fx in (
            await db.execute(
                select(
                    CommercialSkuAssumption.product_id,
                    CommercialSkuAssumption.fx_plan_currency_per_cost_currency,
                ).where(CommercialSkuAssumption.product_id.in_(sorted(product_ids)))
            )
        ).all():
            if fx is not None:
                d.fx_by_product[int(pid)] = float(fx)
    if customer_ids:
        for cid, name in (
            await db.execute(
                select(DimCustomer.id, DimCustomer.name).where(DimCustomer.id.in_(sorted(customer_ids)))
            )
        ).all():
            d.customer_names[int(cid)] = str(name)
    return d


def _build_case_payload(case: CommercialLineupCase, d: _BatchData) -> dict[str, Any]:
    case_id = int(case.id)
    open_channel_customer_id = d.open_channel_customer_id

    def _canon_cust(customer_id: int | None) -> int | None:
        return canonical_open_channel_customer_id(
            customer_id,
            canonical_id=open_channel_customer_id,
            alias_ids=d.open_channel_alias_ids,
        )

    po_rows = d.po_rows.get(case_id, [])
    po_ids = [r[0] for r in po_rows]
    po_label = {r[0]: (r[1] or r[2]) for r in po_rows}
    lineup_lines = d.lines.get(case_id, [])

    planned: dict[tuple[int | None, int], dict[str, float]] = {}
    uom_by_product: dict[int, set[str]] = {}
    for ln in lineup_lines:
        pid = int(ln.product_id)  # type: ignore[arg-type]
        eff_cust = _canon_cust(
            effective_lineup_customer_id(ln, open_channel_customer_id=open_channel_customer_id)
        )
        key = (eff_cust, pid)
        bucket = planned.setdefault(key, {"units": 0.0, "value_plan": 0.0})
        qty = float(ln.quantity_units or 0)
        bucket["units"] += qty
        bucket["value_plan"] += qty * float(ln.dap_evidence_local or 0)
        unit = (ln.base_unit_raw or "").strip()
        if unit:
            uom_by_product.setdefault(pid, set()).add(unit)

    shipped: dict[tuple[int | None, int], dict[str, float]] = {}
    pipeline: dict[tuple[int | None, int], float] = {}
    resolved_customers_on_pos: set[int] = set()
    po_with_shipments: set[int] = set()
    if po_ids:
        for cust_id, pid, units, val in d.shipped_rows.get(case_id, []):
            key = (_canon_cust(int(cust_id) if cust_id is not None else None), int(pid))
            shipped[key] = {"units": float(units), "value_cost": float(val)}
        for cust_id, pid, units in d.pipeline_rows.get(case_id, []):
            key = (_canon_cust(int(cust_id) if cust_id is not None else None), int(pid))
            pipeline[key] = pipeline.get(key, 0.0) + float(units)
        resolved_customers_on_pos = {
            _canon_cust(int(x)) for x in d.resolved_rows.get(case_id, []) if x is not None
        }
        resolved_customers_on_pos.discard(None)
        po_with_shipments = d.po_with_shipments.get(case_id, set())
    po_flags = [
        {"purchase_order_id": pid, "po_number_raw": po_label.get(pid), "flag": "po_no_match"}
        for pid in po_ids
        if pid not in po_with_shipments
    ]

    product_ids = sorted({pid for _c, pid in set(planned) | set(shipped)})
    meta = d.meta
    fx_by_product = d.fx_by_product
    customer_names = d.customer_names

    cust_keys: set[int | None] = {c for c, _ in planned} | {c for c, _ in shipped}
    if not cust_keys and lineup_lines:
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
            pipeline_units = pipeline.get((cust_id, pid), 0.0)
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
                "business_unit": pmeta.get("business_unit"),
                "planned_units": planned_units,
                "shipped_units": shipped_units,
                "pipeline_units": pipeline_units,
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
