"""Enqueue DSI SOH reconciliation after apply completes."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion import ImportJob
from app.services.imports.dsi_soh_reconciliation_sync import run_dsi_soh_reconciliation_sync
from app.services.imports.import_background_slots import (
    SLOT_DSI_SOH,
    set_task_slot_by_job_id,
    set_task_slot_on_job,
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

_dev_soh_reconcile_results: dict[str, dict[str, Any]] = {}


def dev_dsi_soh_reconcile_results() -> dict[str, dict[str, Any]]:
    return _dev_soh_reconcile_results


def enqueue_dsi_soh_reconciliation(
    job_id: int,
    *,
    distributor_id: int,
    period_end_date: date,
    detach_from_caller: bool = True,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)``."""
    payload = {
        "distributor_id": int(distributor_id),
        "period_end_date": period_end_date.isoformat(),
    }
    task_name = "imports.dsi_soh_reconciliation"

    def _run_sync() -> dict[str, Any]:
        return run_dsi_soh_reconciliation_sync(job_id, payload)

    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
    except Exception:
        logger.exception("dsi_soh_reconciliation: Celery enqueue failed job_id=%s", job_id)
        task_id = None

    if task_id:
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        _persist_soh_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    settings = get_settings()
    use_thread = detach_from_caller or settings.cip_dev_celery_dispatch == "in_process_thread"
    task_id = f"dev-soh-reconcile-{uuid.uuid4().hex}"
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
                _dev_soh_reconcile_results[task_id] = {"state": "SUCCESS", "result": out}
            except Exception as exc:
                logger.exception("dsi_soh_reconciliation in-process failed job_id=%s", job_id)
                _dev_soh_reconcile_results[task_id] = {
                    "state": "FAILURE",
                    "error": str(exc)[:800],
                }
                raise

        spawn_in_process_thread_with_ledger(
            task_run_id=task_id,
            thread_name=f"dsi-soh-reconcile-{job_id}",
            target=_in_process,
        )
        _persist_soh_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    def _inline() -> dict[str, Any]:
        out = _run_sync()
        _dev_soh_reconcile_results[task_id] = {"state": "SUCCESS", "result": out}
        return out

    run_inline_with_ledger(task_id, _inline)
    _persist_soh_task_metadata(job_id, task_id, async_poll=False)
    return task_id, False


def _persist_soh_task_metadata(job_id: int, task_id: str, *, async_poll: bool) -> None:
    set_task_slot_by_job_id(int(job_id), SLOT_DSI_SOH, task_id=task_id, async_poll=async_poll)


def dispatch_dsi_soh_reconciliation_after_apply(
    session: Session,
    job: ImportJob,
    *,
    distributor_id: int | None,
    period_end_date: date | None,
) -> None:
    if distributor_id is None or period_end_date is None:
        logger.info(
            "dispatch_dsi_soh_reconciliation_after_apply: skip job_id=%s missing dist or period",
            job.id,
        )
        return
    task_id, async_poll = enqueue_dsi_soh_reconciliation(
        int(job.id),
        distributor_id=int(distributor_id),
        period_end_date=period_end_date,
        detach_from_caller=True,
    )
    set_task_slot_on_job(job, SLOT_DSI_SOH, task_id=task_id, async_poll=async_poll)
    session.add(job)
    session.flush()
