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


# Per-quarter trend keys (plan_vs_executed._compute_trend) for the [period] grain.
_TREND_VALUE_MAP = {
    "fill_rate": "fill_rate",
    "line_hit_rate": "line_hit_rate",
    "over_plan_intake_rate": "deal_stock_units",
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

    grains = {g.lower() for g in req.grains}
    label = period_meta.get("effective_period") or period_meta.get("period_from")

    def metric_value(sc: dict[str, Any]) -> Any:
        """The metric's number from a scorecard (catalog formula: over-plan intake is units)."""
        if metric_key == "no_po_blind_spot":
            npo = sc.get("no_po_blind_spot") or {}
            return npo.get("line_count") if isinstance(npo, dict) else npo
        if metric_key in _SCORECARD_VALUE_MAP:
            return sc.get(_SCORECARD_VALUE_MAP[metric_key])
        return sc.get(metric_key)

    rows: list[dict[str, Any]] = []
    series: list[dict[str, Any]] | None = None
    if metric_key == "volume_bias":
        vb = payload.get("volume_bias") or {}
        total_lines = 0
        weighted = 0.0
        for item in vb.get("by_bu") or []:
            bias = item.get("mean_signed_bias", item.get("mean_bias"))
            rows.append({**item, "bu": item.get("bu"), "value": bias})
            if bias is not None:
                total_lines += int(item.get("line_count") or 0)
                weighted += float(bias) * int(item.get("line_count") or 0)
        value: Any = (weighted / total_lines) if total_lines else None
    elif "bu" in grains:
        value = metric_value(scorecard)
        for pl, sc in (payload.get("scorecard_by_bu") or {}).items():
            rows.append({"period": label, "bu": pl, "value": metric_value(sc)})
        if not rows:
            rows.append({"period": label, "bu": bu, "value": value})
    else:
        value = metric_value(scorecard)
        trend_key = _TREND_VALUE_MAP.get(metric_key)
        trend = payload.get("trend") or []
        if trend_key and trend:
            # One point per quarter in the selected range.
            series = [{"bucket_key": t.get("period_label"), "value": t.get(trend_key)} for t in trend]
            rows = [{"period": t.get("period_label"), "bu": bu, "value": t.get(trend_key)} for t in trend]
        else:
            rows.append({"period": label, "bu": bu, "value": value})

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
        series=series,
        scorecard=scorecard,
        explain={**EXPLAIN, "metric_key": metric_key, "handler": "a1_pve"},
    )
