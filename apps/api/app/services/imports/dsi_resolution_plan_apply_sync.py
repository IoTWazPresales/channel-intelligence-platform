"""Async DSI resolution-plan apply via Celery (reuses apply_dsi_resolution_plan_rows with shared product index)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from app.db.session import AsyncSessionLocal
from app.services.imports.distributor_sales_inventory import _load_product_resolution_index
from app.services.imports.dsi_resolution_plan import apply_dsi_resolution_plan_rows

logger = logging.getLogger(__name__)


def run_dsi_resolution_plan_apply_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Execute plan apply in one asyncio loop; product index loaded once per task."""
    candidate_ids: list[int] = [int(x) for x in payload.get("candidate_ids") or []]
    default_region_id = payload.get("default_region_id")
    default_channel_id = payload.get("default_channel_id")
    default_region_id = int(default_region_id) if default_region_id is not None else None
    default_channel_id = int(default_channel_id) if default_channel_id is not None else None
    partner_tier = payload.get("partner_tier")
    provisional_notes_summary = payload.get("provisional_notes_summary")
    confirm = bool(payload.get("confirm_for_suspicious_distributor_token"))
    overrides = payload.get("overrides")

    total = len(candidate_ids)

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            prod_idx = await db.run_sync(lambda s: _load_product_resolution_index(s))
            chunk = 25
            combined: dict[str, Any] = {
                "import_job_id": job_id,
                "applied": 0,
                "failed": 0,
                "skipped_hold": 0,
                "skipped_not_ready": 0,
                "results": [],
            }
            for start in range(0, total, chunk):
                part = candidate_ids[start : start + chunk]
                if on_progress is not None:
                    on_progress(min(start + len(part), total), total)
                part_out = await apply_dsi_resolution_plan_rows(
                    db,
                    job_id,
                    part,
                    default_region_id=default_region_id,
                    default_channel_id=default_channel_id,
                    partner_tier=partner_tier,
                    provisional_notes_summary=provisional_notes_summary,
                    confirm_for_suspicious_distributor_token=confirm,
                    overrides=overrides,
                    product_index=prod_idx,
                )
                combined["applied"] += int(part_out.get("applied") or 0)
                combined["failed"] += int(part_out.get("failed") or 0)
                combined["skipped_hold"] += int(part_out.get("skipped_hold") or 0)
                combined["skipped_not_ready"] += int(part_out.get("skipped_not_ready") or 0)
                combined["results"].extend(part_out.get("results") or [])
            return combined

    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("dsi_resolution_plan_apply failed job_id=%s", job_id)
        raise
