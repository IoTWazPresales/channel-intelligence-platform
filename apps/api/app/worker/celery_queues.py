"""Celery queue names, routing, and Windows solo dev topology flags (BACKLOG-038/039)."""

from __future__ import annotations

import os
import sys

CELERY_QUEUE_INTERACTIVE = "interactive"
CELERY_QUEUE_BATCH = "batch"
CELERY_QUEUE_DEFAULT = "celery"

INTERACTIVE_TASK_NAMES: frozenset[str] = frozenset(
    {
        "imports.dsi_resolution_plan_compute",
        "imports.dsi_resolution_plan_apply",
        "imports.dsi_bulk_provisional_customers",
        "imports.dsi_bulk_ignore",
        "imports.shipment_bulk_map_customer",
        "imports.shipment_bulk_apply_plans",
        "imports.shipment_bulk_provisional_customers",
        "imports.shipment_bulk_ignore",
        "imports.shipment_resolution_plan_compute",
        "imports.shipment_resolution_plan_apply",
    }
)

BATCH_TASK_NAMES: frozenset[str] = frozenset(
    {
        "imports.process_job",
        "imports.infer_dsi",
        "imports.product_master_commit",
        "imports.product_master_validate",
        "imports.dsi_apply",
        "imports.cpor_historical_apply",
        "imports.shipment_apply",
        "imports.dsi_soh_reconciliation",
        "imports.dsi_velocity_compute",
        "imports.dsi_forecasting",
        "imports.reap_stale_running_jobs",
        "imports.flush_deferred_dsi_post_validate_auto_apply",
        "commercial_planner.parse_lineup_case",
    }
)


def queue_for_task(task_name: str) -> str:
    if task_name in INTERACTIVE_TASK_NAMES:
        return CELERY_QUEUE_INTERACTIVE
    if task_name in BATCH_TASK_NAMES:
        return CELERY_QUEUE_BATCH
    return CELERY_QUEUE_DEFAULT


def build_task_routes() -> dict[str, dict[str, str]]:
    routes: dict[str, dict[str, str]] = {}
    for name in INTERACTIVE_TASK_NAMES:
        routes[name] = {"queue": CELERY_QUEUE_INTERACTIVE}
    for name in BATCH_TASK_NAMES:
        routes[name] = {"queue": CELERY_QUEUE_BATCH}
    return routes


def worker_queue_subscription() -> str:
    """``-Q`` argument: interactive first so solo workers prefer steward work."""
    return f"{CELERY_QUEUE_INTERACTIVE},{CELERY_QUEUE_BATCH},{CELERY_QUEUE_DEFAULT}"


def dev_beat_disabled() -> bool:
    """True when local dev should not run Celery beat / periodic reaper (BACKLOG-038)."""
    if os.environ.get("CIP_DISABLE_DEV_BEAT", "").strip() == "1":
        return True
    if os.environ.get("CIP_ENABLE_DEV_BEAT", "").strip() == "1":
        return False
    if sys.platform == "win32":
        pool = os.environ.get("CIP_CELERY_WORKER_POOL", "solo").strip().lower()
        if pool in ("", "solo"):
            return True
    return False


def defer_dsi_post_validate_auto_apply() -> bool:
    """When true, historical post-validate auto-apply waits for steward idle (BACKLOG-040)."""
    raw = os.environ.get("CIP_DEFER_DSI_POST_VALIDATE_AUTO_APPLY", "").strip()
    if raw == "0":
        return False
    if raw == "1":
        return True
    return sys.platform == "win32"
