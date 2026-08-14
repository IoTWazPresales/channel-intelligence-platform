"""Metric handler registry — keyed by catalog metric key."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.query.handlers import a1_pve, a2_cpor, a3_stock, volume_series
from app.query.types import HandlerResult, QueryRequest

A3_KEYS = frozenset({"channel_stock", "weeks_of_cover", "replenishment_flag"})
A1_KEYS = frozenset(
    {
        "fill_rate",
        "line_hit_rate",
        "over_plan_intake_rate",
        "short_exposure",
        "unplanned_intake",
        "no_po_blind_spot",
        "pipeline_inbound",
        "volume_bias",
    }
)
A2_KEYS = frozenset({"support_spend", "delivery_rate", "support_cost_per_unit_sold"})
VOLUME_KEYS = volume_series.VOLUME_KEYS


async def dispatch_handler(
    db: AsyncSession,
    req: QueryRequest,
    *,
    metric_key: str,
    explain_only: bool = False,
) -> tuple[str, HandlerResult]:
    """Return (handler_name, result). Unknown/unimplemented → not_implemented."""
    key = (metric_key or "").strip().lower()
    if key in A3_KEYS:
        return (
            "a3_stock",
            await a3_stock.handle_a3(db, req, metric_key=key, explain_only=explain_only),
        )
    if key in A1_KEYS:
        return (
            "a1_pve",
            await a1_pve.handle_a1(db, req, metric_key=key, explain_only=explain_only),
        )
    if key in A2_KEYS:
        return (
            "a2_cpor",
            await a2_cpor.handle_a2(db, req, metric_key=key, explain_only=explain_only),
        )
    if key in VOLUME_KEYS:
        return (
            "volume_series",
            await volume_series.handle_volume(db, req, metric_key=key, explain_only=explain_only),
        )
    return (
        "not_implemented",
        HandlerResult(
            status="not_implemented",
            invariants_applied=[],
            message=(
                f"Metric {key!r} is in the governed catalog but has no P3-2 v1 handler. "
                "Owner-surface compute still applies; expand query engine later."
            ),
            explain={
                "handler": None,
                "metric_key": key,
                "v1_handlers": sorted(A3_KEYS | A1_KEYS | A2_KEYS | VOLUME_KEYS),
            },
        ),
    )


def handler_name_for(metric_key: str) -> str | None:
    key = (metric_key or "").strip().lower()
    if key in A3_KEYS:
        return "a3_stock"
    if key in A1_KEYS:
        return "a1_pve"
    if key in A2_KEYS:
        return "a2_cpor"
    if key in VOLUME_KEYS:
        return "volume_series"
    return None


__all__ = [
    "dispatch_handler",
    "handler_name_for",
    "A1_KEYS",
    "A2_KEYS",
    "A3_KEYS",
    "VOLUME_KEYS",
]
