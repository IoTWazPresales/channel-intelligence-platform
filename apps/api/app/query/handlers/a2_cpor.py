"""A2 query handlers — support_spend / delivery_rate / support_cost_per_unit_sold."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session_sync import SessionLocal
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
    # db unused — portfolio path is sync SessionLocal (same as /cpor/intelligence/portfolio)
    _ = db
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

    if explain_only:
        return HandlerResult(
            status="ok",
            invariants_applied=list(INVARIANTS),
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
            message="Would execute build_portfolio_intelligence (no DB run).",
        )

    with SessionLocal() as session:
        payload = build_portfolio_intelligence(session)

    grains = _grain_set(req.grains)
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
            rows.append({**item, "value": item.get(value_key)})
    elif grains in ({"customer", "bu"}, {"period", "customer", "bu"}):
        # Portfolio service lacks customer×BU cross-tab — honest not_implemented
        return HandlerResult(
            status="not_implemented",
            invariants_applied=list(INVARIANTS),
            message=(
                "customer×bu cross-tab is not produced by build_portfolio_intelligence; "
                "use single-dimension grains (customer or bu) for P3-2 v1."
            ),
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
        )
    else:
        # totals / multi without cross-tab
        rows.append({"value": value, **{k: totals.get(k) for k in totals}})

    # Optional filter narrowing
    cust_id = filters.get("customer_id")
    if cust_id is not None and rows and "customer_id" in (rows[0] or {}):
        try:
            cid = int(cust_id)
            rows = [r for r in rows if r.get("customer_id") == cid]
            value = rows[0].get("value") if len(rows) == 1 else value
        except (TypeError, ValueError):
            pass
    bu = filters.get("bu") or filters.get("product_line")
    if bu and rows and "bu" in (rows[0] or {}):
        needle = str(bu).strip().lower()
        rows = [r for r in rows if str(r.get("bu") or "").strip().lower() == needle]
        value = rows[0].get("value") if len(rows) == 1 else value

    return HandlerResult(
        status="ok",
        invariants_applied=list(INVARIANTS),
        data_vintage={
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "cases_in_scope": payload.get("cases_in_scope"),
            "lines_included": payload.get("lines_included"),
            "scope": "all_non_superseded_cases",
        },
        value=value,
        rows=rows,
        scorecard=totals,
        explain={**EXPLAIN, "metric_key": metric_key, "handler": "a2_cpor"},
    )
