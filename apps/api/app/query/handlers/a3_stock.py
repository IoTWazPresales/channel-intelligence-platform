"""A3 query handlers — channel_stock / weeks_of_cover / replenishment_flag.

Default read is the observation series (BACKLOG-097). Live calculator remains for
``explain_only`` and explicit ``woc_source=live`` / ``recompute=1``. No silent fallback.
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
from app.services.woc_observation_read import (
    latest_woc_observations,
    observations_to_stock_vel,
)

INVARIANTS = [
    "latest_per_distributor_product_soh",
    "never_sum_snapshot_history",
    "pod_landed_shipped_only_inbound",
    "pipeline_never_counts",
]

EXPLAIN = {
    "sql_fragments": [
        "weeks_of_cover_observation DISTINCT ON (distributor_id, product_id)",
        "ORDER BY cover_as_of_date DESC, apply-beats-backfill, observed_at DESC",
        "live calculator only for explain_only / woc_source=live",
    ],
    "owner_service": "app.services.woc_observation_read",
}

LIVE_EXPLAIN = {
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


def _wants_live_calculator(filters: dict[str, Any]) -> bool:
    source = str(filters.get("woc_source") or filters.get("source") or "").strip().lower()
    if source == "live":
        return True
    recompute = filters.get("recompute")
    if recompute is True:
        return True
    if str(recompute or "").strip().lower() in {"1", "true", "yes"}:
        return True
    return False


def _payload_from_stock_vel(
    *,
    metric_key: str,
    stock_by_pair: dict[tuple[int, int], float],
    vel_by_pair: dict[tuple[int, int], float],
    woc_source: str,
    extra_vintage: dict[str, Any] | None = None,
) -> HandlerResult:
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

    missing = not stock_by_pair
    vintage = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "grain": "distributor_x_product",
        "pair_count": len(rows),
        "replenishment_threshold_weeks": threshold,
        "woc_source": woc_source,
        "missing_data_alert": missing,
    }
    if extra_vintage:
        vintage.update(extra_vintage)

    return HandlerResult(
        status="ok",
        invariants_applied=list(INVARIANTS),
        data_vintage=vintage,
        value=value,
        rows=rows,
        scorecard={
            "total_channel_stock": total_stock,
            "total_weekly_velocity": total_vel,
            "portfolio_weeks_of_cover": portfolio_woc,
            "portfolio_replenishment_flag": portfolio_flag,
            "pairs_below_threshold": sum(1 for r in rows if r.get("replenishment_flag")),
            "woc_source": woc_source,
            "missing_data_alert": missing,
        },
        explain={**(LIVE_EXPLAIN if woc_source == "live" else EXPLAIN), "metric_key": metric_key, "handler": "a3_stock"},
        message="missing_data" if missing else None,
    )


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
            message="Would read A3 weeks_of_cover_observation current tape (no DB run).",
        )

    dist_id = _opt_int(req.filters, "distributor_id", "distributor")
    prod_id = _opt_int(req.filters, "product_id", "product")
    tid = req.tenant_id

    if _wants_live_calculator(req.filters):
        stock_by_pair = await derived_stock_by_dist_product(
            db, distributor_id=dist_id, tenant_id=tid
        )
        vel_by_pair = await sellout_velocity_52wk_by_dist_product(
            db, distributor_id=dist_id, tenant_id=tid
        )
        if prod_id is not None:
            stock_by_pair = {k: v for k, v in stock_by_pair.items() if k[1] == prod_id}
            vel_by_pair = {k: v for k, v in vel_by_pair.items() if k[1] == prod_id}
        return _payload_from_stock_vel(
            metric_key=metric_key,
            stock_by_pair=stock_by_pair,
            vel_by_pair=vel_by_pair,
            woc_source="live",
        )

    obs = await latest_woc_observations(
        db, tenant_id=tid, distributor_id=dist_id, product_id=prod_id
    )
    stock_by_pair, vel_by_pair = observations_to_stock_vel(obs)
    extra = {}
    if obs:
        extra["cover_as_of_date"] = max(r.cover_as_of_date for r in obs).isoformat()
        extra["observation_trigger"] = obs[0].trigger
    return _payload_from_stock_vel(
        metric_key=metric_key,
        stock_by_pair=stock_by_pair,
        vel_by_pair=vel_by_pair,
        woc_source="observations",
        extra_vintage=extra,
    )
