"""Enqueue WoC observation reconstruct (097-D ops replay / failed-apply retry).

Apply itself runs the same persist function synchronously before report fan-out.
This enqueue is the shared-code replay lever — not a second writer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.config import get_settings
from app.services.imports.import_background_slots import (
    SLOT_WOC_OBSERVATION,
    set_task_slot_by_job_id,
)
from app.services.imports.woc_observation_sync import run_woc_observation_after_apply_sync
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

_dev_results: dict[str, dict[str, Any]] = {}


def enqueue_woc_observation_reconstruct(
    job_id: int,
    payload: dict[str, Any],
    *,
    detach_from_caller: bool = True,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)``."""
    task_name = "imports.woc_observation_reconstruct"

    def _run_sync() -> dict[str, Any]:
        return run_woc_observation_after_apply_sync(int(job_id), payload)

    try:
        result = celery_app.send_task(task_name, args=[int(job_id), payload])
        task_id = str(result.id)
    except Exception:
        logger.exception("woc_observation_reconstruct: Celery enqueue failed job_id=%s", job_id)
        task_id = None

    if task_id:
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        set_task_slot_by_job_id(int(job_id), SLOT_WOC_OBSERVATION, task_id=task_id, async_poll=True)
        return task_id, True

    settings = get_settings()
    use_thread = detach_from_caller or settings.cip_dev_celery_dispatch == "in_process_thread"
    task_id = f"dev-woc-observation-{uuid.uuid4().hex}"
    create_queued_task_run(
        task_run_id=task_id,
        task_name=task_name,
        entity_type=ENTITY_IMPORT_JOB,
        entity_id=job_id,
        transport=TRANSPORT_IN_PROCESS_THREAD if use_thread else TRANSPORT_INLINE_SYNC,
    )
    if use_thread:

        def _in_process() -> None:
            try:
                out = _run_sync()
                _dev_results[task_id] = {"state": "SUCCESS", "result": out}
            except Exception as exc:
                logger.exception("woc_observation_reconstruct in-process failed job_id=%s", job_id)
                _dev_results[task_id] = {"state": "FAILURE", "error": str(exc)[:800]}
                raise

        spawn_in_process_thread_with_ledger(
            task_run_id=task_id,
            thread_name=f"woc-observation-{job_id}",
            target=_in_process,
        )
        set_task_slot_by_job_id(int(job_id), SLOT_WOC_OBSERVATION, task_id=task_id, async_poll=True)
        return task_id, True

    def _inline() -> dict[str, Any]:
        out = _run_sync()
        _dev_results[task_id] = {"state": "SUCCESS", "result": out}
        return out

    run_inline_with_ledger(task_id, _inline)
    set_task_slot_by_job_id(int(job_id), SLOT_WOC_OBSERVATION, task_id=task_id, async_poll=False)
    return task_id, False
