"""Enqueue DSI resolution-plan apply (Celery, dev in-process thread, or detached daemon thread)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.core.config import get_settings
from app.services.imports.dsi_resolution_plan_apply_sync import run_dsi_resolution_plan_apply_sync
from app.services.imports.dsi_resolution_plan_compute_sync import run_dsi_resolution_plan_compute_sync
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

# Populated by mappings endpoint dev fallback; post-validate only needs enqueue + metadata.
_dev_dsi_bulk_task_results: dict[str, dict[str, Any]] = {}


def dev_dsi_bulk_task_results() -> dict[str, dict[str, Any]]:
    return _dev_dsi_bulk_task_results


def enqueue_dsi_resolution_plan_apply(
    job_id: int,
    payload: dict[str, Any],
    *,
    detach_from_caller: bool = False,
    on_complete: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)``.

    When ``detach_from_caller`` is True (post-validate auto-apply), never run
    ``asyncio.run`` on the caller thread — avoids the Windows Celery solo-pool hang that
    disabled the original post-validate hook.
    """
    settings = get_settings()
    task_name = "imports.dsi_resolution_plan_apply"

    def _run_sync() -> dict[str, Any]:
        return run_dsi_resolution_plan_apply_sync(job_id, payload)

    def _finish(out: dict[str, Any], *, state: str, error: str | None = None) -> None:
        if on_complete is not None:
            on_complete(out)

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
        logger.exception(
            "dsi_resolution_plan_apply: Celery enqueue failed job_id=%s task=%s", job_id, task_name
        )

    use_thread = detach_from_caller or settings.cip_dev_celery_dispatch == "in_process_thread"
    if use_thread:
        task_id = f"dev-plan-apply-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_IN_PROCESS_THREAD,
        )

        def _in_process() -> None:
            try:
                out = _run_sync()
                _dev_dsi_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
                _finish(out, state="SUCCESS")
            except Exception as exc:
                logger.exception(
                    "dsi_resolution_plan_apply in-process failed job_id=%s task_id=%s",
                    job_id,
                    task_id,
                )
                _dev_dsi_bulk_task_results[task_id] = {
                    "state": "FAILURE",
                    "error": str(exc)[:800],
                }
                _finish({}, state="FAILURE", error=str(exc))
                raise

        spawn_in_process_thread_with_ledger(
            task_run_id=task_id,
            thread_name=f"dsi-plan-apply-{job_id}",
            target=_in_process,
        )
        return task_id, True

    task_id = f"sync-plan-apply-{uuid.uuid4().hex}"
    create_queued_task_run(
        task_run_id=task_id,
        task_name=task_name,
        entity_type=ENTITY_IMPORT_JOB,
        entity_id=job_id,
        transport=TRANSPORT_INLINE_SYNC,
    )

    def _inline() -> dict[str, Any]:
        out = _run_sync()
        _dev_dsi_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
        _finish(out, state="SUCCESS")
        return out

    run_inline_with_ledger(task_id, _inline)
    return task_id, False


def enqueue_dsi_resolution_plan_compute(
    job_id: int,
    payload: dict[str, Any],
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)`` for read-only plan generation."""
    settings = get_settings()
    task_name = "imports.dsi_resolution_plan_compute"

    def _run_sync() -> dict[str, Any]:
        return run_dsi_resolution_plan_compute_sync(job_id, payload)

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
        logger.exception(
            "dsi_resolution_plan_compute: Celery enqueue failed job_id=%s task=%s", job_id, task_name
        )

    if settings.cip_dev_celery_dispatch == "in_process_thread":
        task_id = f"dev-plan-compute-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_IN_PROCESS_THREAD,
        )

        def _in_process() -> None:
            try:
                out = _run_sync()
                _dev_dsi_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
            except Exception as exc:
                logger.exception(
                    "dsi_resolution_plan_compute in-process failed job_id=%s task_id=%s",
                    job_id,
                    task_id,
                )
                _dev_dsi_bulk_task_results[task_id] = {
                    "state": "FAILURE",
                    "error": str(exc)[:800],
                }
                raise

        spawn_in_process_thread_with_ledger(
            task_run_id=task_id,
            thread_name=f"dsi-plan-compute-{job_id}",
            target=_in_process,
        )
        return task_id, True

    task_id = f"sync-plan-compute-{uuid.uuid4().hex}"
    create_queued_task_run(
        task_run_id=task_id,
        task_name=task_name,
        entity_type=ENTITY_IMPORT_JOB,
        entity_id=job_id,
        transport=TRANSPORT_INLINE_SYNC,
    )

    def _inline() -> dict[str, Any]:
        out = _run_sync()
        _dev_dsi_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
        return out

    run_inline_with_ledger(task_id, _inline)
    return task_id, False
