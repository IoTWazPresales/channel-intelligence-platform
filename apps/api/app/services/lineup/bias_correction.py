"""Load A1 volume-bias map for B2 net-requirement correction."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.commercial_planner.plan_vs_executed import (
    buy_plan_bias_factors,
    collect_execution_rows,
    compute_volume_bias,
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
        rows = await collect_execution_rows(
            db,
            period_from=period_from,
            period_to=period_to,
            product_line=None,
        )
        vb = compute_volume_bias(rows)
        by_bu = buy_plan_bias_factors(vb)
        return {
            "period_from": period_from,
            "period_to": period_to,
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
