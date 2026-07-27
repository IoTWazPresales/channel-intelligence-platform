"""Enqueue CPOR historical resolution-plan compute/apply (Unit C, D-013).

Mirrors ``app.services.imports.shipment_bulk_steward_enqueue.enqueue_shipment_bulk_task``:
broker first, dev in-process thread on enqueue failure (when
``CIP_DEV_CELERY_DISPATCH=in_process_thread``), else inline sync fallback. The dev/sync
fallback result store lets the HTTP poll endpoint return the transient plan/apply result even
when Celery is unavailable, exactly like the shipment steward bulk tasks.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.services.cpor.historical_import.resolution_plan_apply_sync import (
    run_cpor_historical_resolution_plan_apply_sync as _apply_sync,
)
from app.services.cpor.historical_import.resolution_plan_compute_sync import (
    run_cpor_historical_resolution_plan_compute_sync as _compute_sync,
)
from app.services.task_run_ledger import (
    ENTITY_IMPORT_JOB,
    TRANSPORT_BROKER,
    TRANSPORT_INLINE_SYNC,
    TRANSPORT_IN_PROCESS_THREAD,
    create_queued_task_run,
    run_inline_with_ledger,
    spawn_in_process_thread_with_ledger,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Task names registered in app.worker.tasks.
TASK_CPOR_RESOLUTION_PLAN_COMPUTE = "imports.cpor_historical_resolution_plan_compute"
TASK_CPOR_RESOLUTION_PLAN_APPLY = "imports.cpor_historical_resolution_plan_apply"

# Dev/sync-fallback result store (mirrors shipment bulk dev store), keyed by synthetic task id.
_dev_cpor_resolution_plan_task_results: dict[str, dict[str, Any]] = {}


def dev_cpor_resolution_plan_task_results() -> dict[str, dict[str, Any]]:
    return _dev_cpor_resolution_plan_task_results


def run_cpor_historical_resolution_plan_compute_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    return _compute_sync(job_id, payload, on_progress=on_progress)


def run_cpor_historical_resolution_plan_apply_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    return _apply_sync(job_id, payload, on_progress=on_progress)


def enqueue_cpor_resolution_plan_task(
    *,
    task_name: str,
    job_id: int,
    payload: dict[str, Any],
    run_sync: Callable[[], dict[str, Any]],
    dev_prefix: str,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)`` — broker → dev in-process thread → inline sync."""
    settings = get_settings()
    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        return task_id, True
    except Exception:
        logger.exception("cpor_resolution_plan: Celery enqueue failed job_id=%s task=%s", job_id, task_name)
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"dev-{dev_prefix}-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_id,
                task_name=task_name,
                entity_type=ENTITY_IMPORT_JOB,
                entity_id=job_id,
                transport=TRANSPORT_IN_PROCESS_THREAD,
            )

            def _in_process() -> None:
                try:
                    out = run_sync()
                    _dev_cpor_resolution_plan_task_results[task_id] = {"state": "SUCCESS", "result": out}
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "cpor_resolution_plan in-process thread failed job_id=%s task_id=%s", job_id, task_id
                    )
                    _dev_cpor_resolution_plan_task_results[task_id] = {
                        "state": "FAILURE",
                        "error": str(exc)[:800],
                    }
                    raise

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: cpor_resolution_plan %s job_id=%s — in-process thread (DEV ONLY).",
                task_name,
                job_id,
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_id,
                thread_name=f"{dev_prefix}-{job_id}",
                target=_in_process,
            )
            return task_id, True

        task_id = f"sync-{dev_prefix}-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_INLINE_SYNC,
        )

        def _inline() -> dict[str, Any]:
            out = run_sync()
            _dev_cpor_resolution_plan_task_results[task_id] = {"state": "SUCCESS", "result": out}
            return out

        run_inline_with_ledger(task_id, _inline)
        return task_id, False
