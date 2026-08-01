"""Load A1 volume-bias map for B2 net-requirement correction."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.commercial_planner.plan_vs_executed import (
    collect_execution_rows,
    compute_volume_bias,
    coverage,
    lineup_linked_year_quarters,
    periods_from_coverage,
    resolve_default_period,
)

logger = logging.getLogger(__name__)


async def volume_bias_by_bu(
    db: AsyncSession,
    *,
    period_from: str | None = None,
    period_to: str | None = None,
) -> dict[str, Any]:
    """Return ``{bu: mean_signed_bias}`` plus metadata. Empty map on failure."""
    try:
        cov = await coverage(db)
        all_periods = periods_from_coverage(cov)
        lineup_quarters = await lineup_linked_year_quarters(db)
        default_period = resolve_default_period(
            all_periods,
            coverage_groups=cov.get("groups"),
            lineup_linked_quarters=lineup_quarters,
        )
        effective_from = period_from or default_period
        effective_to = period_to or default_period
        rows = await collect_execution_rows(
            db,
            period_from=effective_from,
            period_to=effective_to,
            product_line=None,
        )
        vb = compute_volume_bias(rows)
        by_bu = {
            str(item["bu"]): float(item["mean_signed_bias"])
            for item in (vb.get("by_bu") or [])
            if item.get("bu") is not None
        }
        return {
            "period_from": effective_from,
            "period_to": effective_to,
            "by_bu": by_bu,
            "pm_attribution": vb.get("pm_attribution"),
            "available": bool(by_bu),
        }
    except Exception:
        logger.exception("volume_bias_by_bu failed")
        return {
            "period_from": period_from,
            "period_to": period_to,
            "by_bu": {},
            "available": False,
            "error": "bias_unavailable",
        }
