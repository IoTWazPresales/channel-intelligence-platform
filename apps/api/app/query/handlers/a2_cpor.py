"""A2 query handlers — support_spend / delivery_rate / support_cost_per_unit_sold."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.query.types import HandlerResult, QueryRequest
from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence

INVARIANTS = [
    "voided_and_zero_estimate_excluded",
    "usd_compute_zar_display",
    "claim_rate_not_fabricated",
]

EXPLAIN = {
    "owner_service": "app.services.cpor.portfolio_intelligence",
    "sql_fragments": [
        "SELECT non-superseded cpor_case + lines (joinedload)",
        "Python rollup by customer / BU / promo_type",
    ],
    "note": "Portfolio intelligence is all-time over non-superseded cases; period filter not supported.",
}


def _grain_set(grains: list[str]) -> set[str]:
    return {str(g).strip().lower() for g in grains if str(g).strip()}


async def handle_a2(
    db: AsyncSession,
    req: QueryRequest,
    *,
    metric_key: str,
    explain_only: bool = False,
) -> HandlerResult:
    filters = req.filters or {}
    if filters.get("period_from") or filters.get("period_to") or filters.get("period"):
        return HandlerResult(
            status="not_implemented",
            invariants_applied=list(INVARIANTS),
            message=(
                "A2 portfolio intelligence has no period filter today — refusing silent "
                "all-time numbers when period was requested. Use owner surface or omit period."
            ),
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
        )

    def refuse(message: str) -> HandlerResult:
        return HandlerResult(status="refused", message=message, invariants_applied=list(INVARIANTS),
                             explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"})

    unknown = set(filters) - {"customer_id", "bu", "product_line", "period", "period_from", "period_to", "period_grain"}
    if unknown:
        return refuse(f"A2 portfolio intelligence cannot be filtered by {', '.join(sorted(unknown))}.")
    cust_id = filters.get("customer_id")
    if cust_id is not None:
        if isinstance(cust_id, bool) or not isinstance(cust_id, (str, int)):
            return refuse("customer_id must be one whole-number customer id.")
        try:
            cust_id = int(cust_id)
        except (TypeError, ValueError):
            return refuse("customer_id must be one whole-number customer id.")
    for key in ("bu", "product_line"):
        if key in filters and (not isinstance(filters[key], str) or not filters[key].strip()):
            return refuse(f"{key} must be one non-empty product line.")
    bu = filters.get("bu") or filters.get("product_line")
    if "bu" in filters and "product_line" in filters and filters["bu"].strip().casefold() != filters["product_line"].strip().casefold():
        return refuse("bu and product_line must name the same product line.")

    grains = _grain_set(req.grains)
    if grains in ({"customer", "bu"}, {"period", "customer", "bu"}):
        return HandlerResult(
            status="not_implemented", invariants_applied=list(INVARIANTS),
            message="customer×bu cross-tab is not produced by build_portfolio_intelligence; use single-dimension grains (customer or bu) for P3-2 v1.",
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
        )

    if explain_only:
        return HandlerResult(
            status="ok",
            invariants_applied=list(INVARIANTS),
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
            message="Would execute build_portfolio_intelligence (no DB run).",
        )

    payload = await db.run_sync(
        build_portfolio_intelligence, tenant_id=req.tenant_id, customer_id=cust_id,
        bu=bu, include_incremental=False,
    )

    totals = payload.get("totals") or {}

    if metric_key == "support_spend":
        value_key = "support_usd"
        value: Any = totals.get("support_usd")
    elif metric_key == "delivery_rate":
        value_key = "delivery_rate"
        value = totals.get("delivery_rate")
    else:
        value_key = "support_per_unit_sold_usd"
        value = totals.get("support_per_unit_sold_usd")

    rows: list[dict[str, Any]] = []
    if grains == {"customer"} or grains == {"period", "customer"}:
        for item in payload.get("by_customer") or []:
            rows.append({**item, "value": item.get(value_key)})
    elif grains == {"bu"} or grains == {"period", "bu"}:
        for item in payload.get("by_bu") or []:
            rows.append({**item, "value": item.get(value_key)})
    elif grains == {"promo_type"} or "promo_type" in grains:
        for item in payload.get("by_promotion_type") or []:
            rows.append({**item, "promo_type": item.get("promotion_type"), "value": item.get(value_key)})
    else:
        # totals / multi without cross-tab
        rows.append({"value": value, **{k: totals.get(k) for k in totals}})

    return HandlerResult(
        status="ok",
        invariants_applied=list(INVARIANTS),
        data_vintage={
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "cases_in_scope": payload.get("cases_in_scope"),
            "lines_included": payload.get("lines_included"),
            "scope": "filtered_non_superseded_cases",
        },
        value=value,
        rows=rows,
        scorecard=totals,
        explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
    )
