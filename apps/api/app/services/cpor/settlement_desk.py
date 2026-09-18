"""Read-only settlement-desk grains.

CIP qty is CST (fact_customer_sellthrough) at product grain for the case customer.
Customer qty is claim rollup on cpor_case_line.result_qty.
Does not write or redefine stored columns.
"""

from __future__ import annotations

from typing import Any

CORROBORATION_REASON: dict[str, str] = {
    "match": "Agrees with CIP",
    "pending": "Awaiting customer",
    "cip_only": "CIP only",
    "mismatch": "Mismatch",
    "customer_only": "Customer only",
}


def classify_corroboration(
    *,
    cip_qty: float | None,
    customer_qty: float | None,
    has_customer_report: bool,
) -> str:
    """Chip vocab used by the A desk. Exact equality — not the 10% CST FLAG."""
    if not has_customer_report or customer_qty is None:
        return "pending"
    cip = 0.0 if cip_qty is None else float(cip_qty)
    cust = float(customer_qty)
    if cust == 0 and cip > 0:
        return "cip_only"
    if cip == 0 and cust > 0:
        return "customer_only"
    if cip_qty is None:
        return "pending"
    if abs(cip - cust) < 1e-9:
        return "match"
    return "mismatch"


def line_amount(qty: float | None, support_unit: float | None) -> float | None:
    if qty is None or support_unit is None:
        return None
    return float(qty) * float(support_unit)


def cip_amount_product_grain(lines: list[dict[str, Any]]) -> float | None:
    """CST is per product_id. Summing the same CST across duplicate case lines would double-count."""
    seen: set[int] = set()
    total = 0.0
    any_cip = False
    for row in lines:
        pid = row.get("product_id")
        cip = row.get("cip_qty")
        support = row.get("support_unit")
        if pid is None or cip is None or support is None:
            continue
        key = int(pid)
        if key in seen:
            continue
        seen.add(key)
        total += float(cip) * float(support)
        any_cip = True
    return total if any_cip else None


def customer_amount_line_grain(lines: list[dict[str, Any]]) -> float | None:
    total = 0.0
    any_cust = False
    for row in lines:
        amt = line_amount(row.get("customer_qty"), row.get("support_unit"))
        if amt is None:
            continue
        total += amt
        any_cust = True
    return total if any_cust else None
