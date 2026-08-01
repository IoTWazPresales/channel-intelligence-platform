"""A3 query handlers — channel_stock / weeks_of_cover / replenishment_flag.

Reuses channel_ops_derived_stock (latest-per-snapshot; POD-landed only; no pipeline).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.query.types import HandlerResult, QueryRequest
from app.services.channel_ops_config import REPLENISHMENT_WOC_THRESHOLD_WEEKS
from app.services.channel_ops_derived_stock import (
    derived_stock_by_dist_product,
    replenishment_flag_v1,
    sellout_velocity_52wk_by_dist_product,
    weeks_of_cover_or_none,
)

INVARIANTS = [
    "latest_per_distributor_product_soh",
    "never_sum_snapshot_history",
    "pod_landed_shipped_only_inbound",
    "pipeline_never_counts",
]

EXPLAIN = {
    "sql_fragments": [
        "MAX(fact_inventory_distributor.as_of_date) GROUP BY distributor_id, product_id",
        "sell-out units WHERE transaction_date > snapshot_date",
        "inbound WHERE pod_date > snapshot AND line_state=shipped",
    ],
    "owner_service": "app.services.channel_ops_derived_stock",
}


def _opt_int(filters: dict[str, Any], *keys: str) -> int | None:
    for k in keys:
        raw = filters.get(k)
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


async def handle_a3(
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
            explain={**EXPLAIN, "metric_key": metric_key, "handler": "a3_stock"},
            message="Would execute A3 derived stock / WoC path (no DB run).",
        )

    dist_id = _opt_int(req.filters, "distributor_id", "distributor")
    prod_id = _opt_int(req.filters, "product_id", "product")
    tid = req.tenant_id

    stock_by_pair = await derived_stock_by_dist_product(
        db, distributor_id=dist_id, tenant_id=tid
    )
    vel_by_pair = await sellout_velocity_52wk_by_dist_product(
        db, distributor_id=dist_id, tenant_id=tid
    )

    if prod_id is not None:
        stock_by_pair = {k: v for k, v in stock_by_pair.items() if k[1] == prod_id}
        vel_by_pair = {k: v for k, v in vel_by_pair.items() if k[1] == prod_id}

    threshold = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)
    rows: list[dict[str, Any]] = []
    for (d_id, p_id), stock in sorted(stock_by_pair.items()):
        vel = vel_by_pair.get((d_id, p_id))
        woc = weeks_of_cover_or_none(stock, vel)
        flag = replenishment_flag_v1(woc, threshold_weeks=threshold)
        row: dict[str, Any] = {
            "distributor_id": d_id,
            "product_id": p_id,
            "channel_stock": stock,
            "weekly_velocity": vel,
            "weeks_of_cover": woc,
            "replenishment_flag": flag,
        }
        if metric_key == "channel_stock":
            row["value"] = stock
        elif metric_key == "weeks_of_cover":
            row["value"] = woc
        else:
            row["value"] = flag
        rows.append(row)

    total_stock = float(sum(stock_by_pair.values())) if stock_by_pair else 0.0
    total_vel = float(sum(vel_by_pair.values())) if vel_by_pair else 0.0
    portfolio_woc = weeks_of_cover_or_none(total_stock, total_vel or None)
    portfolio_flag = replenishment_flag_v1(portfolio_woc, threshold_weeks=threshold)

    if metric_key == "channel_stock":
        value: Any = total_stock
    elif metric_key == "weeks_of_cover":
        value = portfolio_woc
    else:
        value = portfolio_flag

    return HandlerResult(
        status="ok",
        invariants_applied=list(INVARIANTS),
        data_vintage={
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "grain": "distributor_x_product",
            "pair_count": len(rows),
            "replenishment_threshold_weeks": threshold,
        },
        value=value,
        rows=rows,
        scorecard={
            "total_channel_stock": total_stock,
            "total_weekly_velocity": total_vel,
            "portfolio_weeks_of_cover": portfolio_woc,
            "portfolio_replenishment_flag": portfolio_flag,
            "pairs_below_threshold": sum(1 for r in rows if r.get("replenishment_flag")),
        },
        explain={**EXPLAIN, "metric_key": metric_key, "handler": "a3_stock"},
    )
