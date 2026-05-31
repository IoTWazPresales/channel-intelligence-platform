"""Enqueue DSI forecasting after velocity compute completes."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion import ImportJob
from app.services.imports.dsi_forecasting_sync import run_dsi_forecasting_sync
from app.services.imports.import_background_slots import (
    SLOT_DSI_FORECASTING,
    set_task_slot_by_job_id,
    set_task_slot_on_job,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_dev_forecasting_results: dict[str, dict[str, Any]] = {}


def dev_dsi_forecasting_results() -> dict[str, dict[str, Any]]:
    return _dev_forecasting_results


def enqueue_dsi_forecasting(
    job_id: int,
    *,
    distributor_id: int,
    detach_from_caller: bool = True,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)``."""
    payload = {
        "distributor_id": int(distributor_id),
    }
    task_name = "imports.dsi_forecasting"

    def _run_sync() -> dict[str, Any]:
        return run_dsi_forecasting_sync(job_id, payload)

    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
    except Exception:
        logger.exception("dsi_forecasting: Celery enqueue failed job_id=%s", job_id)
        task_id = None

    if task_id:
        _persist_forecasting_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    settings = get_settings()
    use_thread = detach_from_caller or settings.cip_dev_celery_dispatch == "in_process_thread"
    task_id = f"dev-forecasting-{uuid.uuid4().hex}"

    if use_thread:

        def _in_process() -> None:
            try:
                out = _run_sync()
                _dev_forecasting_results[task_id] = {"state": "SUCCESS", "result": out}
            except Exception as exc:
                logger.exception("dsi_forecasting in-process failed job_id=%s", job_id)
                _dev_forecasting_results[task_id] = {
                    "state": "FAILURE",
                    "error": str(exc)[:800],
                }

        threading.Thread(
            target=_in_process,
            name=f"dsi-forecasting-{job_id}",
            daemon=True,
        ).start()
        _persist_forecasting_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    out = _run_sync()
    _dev_forecasting_results[task_id] = {"state": "SUCCESS", "result": out}
    _persist_forecasting_task_metadata(job_id, task_id, async_poll=False)
    return task_id, False


def _persist_forecasting_task_metadata(job_id: int, task_id: str, *, async_poll: bool) -> None:
    set_task_slot_by_job_id(int(job_id), SLOT_DSI_FORECASTING, task_id=task_id, async_poll=async_poll)


def dispatch_dsi_forecasting_after_velocity(
    session: Session,
    job: ImportJob,
    distributor_id: int,
) -> None:
    task_id, async_poll = enqueue_dsi_forecasting(
        int(job.id),
        distributor_id=int(distributor_id),
        detach_from_caller=True,
    )
    set_task_slot_on_job(job, SLOT_DSI_FORECASTING, task_id=task_id, async_poll=async_poll)
    session.add(job)
    session.flush()
