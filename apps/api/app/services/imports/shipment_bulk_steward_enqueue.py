"""Enqueue shipment steward bulk ops (Celery → dev in-process thread → sync fallback).

Mirrors ``mappings._enqueue_dsi_bulk_provisional_customers`` / ``dsi_resolution_plan_enqueue`` so the
three shipment bulk steward operations (map-customer, apply-confirmed-plans, create-provisional-
customers) run as background Celery tasks with progress instead of blocking the HTTP request (which
risked a proxy timeout on large jobs). The sync wrappers also serve as the broker-failure fallback,
so behaviour degrades to inline execution only when the broker is unavailable and no dev thread is
configured — never silently for normal operation.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Callable

from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session_sync import SessionLocal
from app.services.imports.shipment_evidence_steward_ops import (
    execute_bulk_apply_shipment_candidate_plans,
    execute_bulk_create_provisional_shipment_customers,
    execute_bulk_map_shipment_customers,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Task names registered in app.worker.tasks.
TASK_SHIPMENT_BULK_MAP_CUSTOMER = "imports.shipment_bulk_map_customer"
TASK_SHIPMENT_BULK_APPLY_PLANS = "imports.shipment_bulk_apply_plans"
TASK_SHIPMENT_BULK_PROVISIONAL_CUSTOMERS = "imports.shipment_bulk_provisional_customers"

# Dev/sync-fallback result store (mirrors dsi bulk dev store), keyed by synthetic task id.
_dev_shipment_bulk_task_results: dict[str, dict[str, Any]] = {}


def dev_shipment_bulk_task_results() -> dict[str, dict[str, Any]]:
    return _dev_shipment_bulk_task_results


# --- Sync wrappers (used by Celery tasks AND the broker-failure fallback) -------


def _coerce_per_candidate_display_names(raw: Any) -> dict[int, str]:
    per: dict[int, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                per[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
    return per


def run_shipment_bulk_map_customer_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    with SessionLocal() as db:
        return execute_bulk_map_shipment_customers(
            db,
            customer_id=int(payload["customer_id"]),
            candidate_ids=[int(x) for x in payload.get("candidate_ids", [])],
            on_progress=on_progress,
        )


def run_shipment_bulk_apply_plans_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    with SessionLocal() as db:
        return execute_bulk_apply_shipment_candidate_plans(
            db,
            import_job_id=int(job_id),
            candidate_ids=[int(x) for x in payload.get("candidate_ids", [])],
            on_progress=on_progress,
        )


def run_shipment_bulk_provisional_customers_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    with SessionLocal() as db:
        return execute_bulk_create_provisional_shipment_customers(
            db,
            job_id=int(job_id),
            candidate_ids=[int(x) for x in payload.get("candidate_ids", [])],
            per_candidate_display_name=_coerce_per_candidate_display_names(payload.get("display_names")),
            region_id=payload.get("region_id"),
            channel_id=payload.get("channel_id"),
            preferred_distributor_id=payload.get("preferred_distributor_id"),
            partner_tier=payload.get("partner_tier"),
            notes_summary=payload.get("notes_summary"),
            on_progress=on_progress,
        )


# --- Enqueue (broker → dev thread → sync fallback) ------------------------------


def enqueue_shipment_bulk_task(
    *,
    task_name: str,
    job_id: int,
    payload: dict[str, Any],
    run_sync: Callable[[], dict[str, Any]],
    dev_prefix: str,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)``.

    Tries the real broker first (``async_poll_required=True``). On enqueue failure falls back to a
    dev in-process thread when ``CIP_DEV_CELERY_DISPATCH=in_process_thread`` (still pollable), else
    runs inline and returns ``async_poll_required=False`` with the result already in the dev store.
    """
    settings = get_settings()
    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        return str(result.id), True
    except Exception:
        logger.exception("shipment_bulk: Celery enqueue failed job_id=%s task=%s", job_id, task_name)
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"dev-{dev_prefix}-{uuid.uuid4().hex}"

            def _in_process() -> None:
                try:
                    out = run_sync()
                    _dev_shipment_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "shipment_bulk in-process thread failed job_id=%s task_id=%s", job_id, task_id
                    )
                    _dev_shipment_bulk_task_results[task_id] = {"state": "FAILURE", "error": str(exc)[:800]}

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: shipment_bulk %s job_id=%s — in-process thread (DEV ONLY).", task_name, job_id
            )
            threading.Thread(target=_in_process, name=f"{dev_prefix}-{job_id}", daemon=True).start()
            return task_id, True

        out = run_sync()
        task_id = f"sync-{dev_prefix}-{uuid.uuid4().hex}"
        _dev_shipment_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
        return task_id, False
