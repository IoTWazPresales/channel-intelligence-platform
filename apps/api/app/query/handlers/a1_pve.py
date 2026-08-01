"""A1 query handlers — plan-vs-executed scorecard family (shipped-only fill)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.query.types import HandlerResult, QueryRequest
from app.services.commercial_planner.plan_vs_executed import plan_vs_executed_read_model

INVARIANTS = [
    "shipped_only_fill",
    "line_state_shipped_evidence",
    "pipeline_excluded_from_fill_numerator",
    "in_plan_rows_planned_gt_zero",
]

EXPLAIN = {
    "owner_service": "app.services.commercial_planner.plan_vs_executed",
    "sql_fragments": [
        "shipment evidence SUM(quantity) WHERE line_state='shipped' GROUP BY customer, product",
        "open_order → pipeline_units only (never fill numerator)",
    ],
}

_SCORECARD_VALUE_MAP = {
    "fill_rate": "fill_rate",
    "line_hit_rate": "line_hit_rate",
    "over_plan_intake_rate": "over_plan_intake_units",
    "short_exposure": "short_exposure_units",
    "unplanned_intake": "unplanned_intake_units",
    "pipeline_inbound": "pipeline_units_in_plan",
}


async def handle_a1(
    db: AsyncSession,
    req: QueryRequest,
    *,
    metric_key: str,
    explain_only: bool = False,
) -> HandlerResult:
    if explain_only:
        return HandlerResult(
            status="ok",
            invariants_applied=list(INVARIANTS),
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a1_pve"},
            message="Would execute plan_vs_executed_read_model (no DB run).",
        )

    filters = req.filters or {}
    period_from = filters.get("period_from") or filters.get("period")
    period_to = filters.get("period_to") or filters.get("period")
    bu = filters.get("bu") or filters.get("product_line") or filters.get("drill_bu")
    if bu is not None:
        bu = str(bu).strip() or None

    # Grain includes period → require period context (default resolved inside read model).
    payload = await plan_vs_executed_read_model(
        db,
        period_from=str(period_from).strip() if period_from else None,
        period_to=str(period_to).strip() if period_to else None,
        product_line=bu,
        drill_bu=bu,
    )
    if payload.get("data_unavailable"):
        return HandlerResult(
            status="ok",
            invariants_applied=list(INVARIANTS),
            data_vintage={"as_of_utc": datetime.now(timezone.utc).isoformat()},
            value=None,
            rows=[],
            scorecard=None,
            message="Plan-vs-executed data unavailable.",
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a1_pve"},
        )

    scorecard = payload.get("scorecard") or {}
    period_range = payload.get("period_range") or {}
    period_meta = {
        "period_from": period_range.get("from") or period_from,
        "period_to": period_range.get("to") or period_to,
        "effective_period": period_range.get("from") or payload.get("default_period"),
    }

    if metric_key == "no_po_blind_spot":
        value: Any = scorecard.get("no_po_blind_spot")
    elif metric_key == "volume_bias":
        value = payload.get("volume_bias")
    elif metric_key in _SCORECARD_VALUE_MAP:
        value = scorecard.get(_SCORECARD_VALUE_MAP[metric_key])
        # over_plan_intake_rate: expose as rate when planned > 0
        if metric_key == "over_plan_intake_rate":
            planned = float(scorecard.get("planned_units") or 0)
            over_u = float(scorecard.get("over_plan_intake_units") or scorecard.get("deal_stock_units") or 0)
            value = (over_u / planned) if planned > 0 else None
    else:
        value = scorecard.get(metric_key)

    rows: list[dict[str, Any]] = []
    if metric_key == "volume_bias":
        vb = payload.get("volume_bias") or {}
        for item in vb.get("by_bu") or []:
            rows.append({"bu": item.get("bu"), "value": item.get("mean_bias"), **item})
    elif "bu" in {g.lower() for g in req.grains}:
        # BU grain: surface volume_bias BU rows when available; else single portfolio value
        vb = payload.get("volume_bias") or {}
        for item in vb.get("by_bu") or []:
            rows.append({"bu": item.get("bu"), "value": item.get("mean_bias"), **item})
        if not rows:
            rows.append({"period": period_meta.get("effective_period"), "bu": bu, "value": value})
    else:
        rows.append(
            {
                "period": period_meta.get("effective_period")
                or period_meta.get("period_from"),
                "bu": bu,
                "value": value,
            }
        )

    return HandlerResult(
        status="ok",
        invariants_applied=list(INVARIANTS),
        data_vintage={
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in period_meta.items() if v is not None},
            "row_count": len(payload.get("drill_rows") or []),
        },
        value=value,
        rows=rows,
        scorecard=scorecard,
        explain={**EXPLAIN, "metric_key": metric_key, "handler": "a1_pve"},
    )
