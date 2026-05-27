"""Enqueue DSI velocity compute after apply completes."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion import ImportJob
from app.services.imports.dsi_velocity_sync import run_dsi_velocity_compute_sync
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_dev_velocity_compute_results: dict[str, dict[str, Any]] = {}


def dev_dsi_velocity_compute_results() -> dict[str, dict[str, Any]]:
    return _dev_velocity_compute_results


def enqueue_dsi_velocity_compute(
    job_id: int,
    *,
    distributor_id: int,
    detach_from_caller: bool = True,
) -> tuple[str, bool]:
    """Return ``(task_id, async_poll_required)``."""
    payload = {
        "distributor_id": int(distributor_id),
    }
    task_name = "imports.dsi_velocity_compute"

    def _run_sync() -> dict[str, Any]:
        return run_dsi_velocity_compute_sync(job_id, payload)

    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
    except Exception:
        logger.exception("dsi_velocity_compute: Celery enqueue failed job_id=%s", job_id)
        task_id = None

    if task_id:
        _persist_velocity_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    settings = get_settings()
    use_thread = detach_from_caller or settings.cip_dev_celery_dispatch == "in_process_thread"
    task_id = f"dev-velocity-compute-{uuid.uuid4().hex}"

    if use_thread:

        def _in_process() -> None:
            try:
                out = _run_sync()
                _dev_velocity_compute_results[task_id] = {"state": "SUCCESS", "result": out}
            except Exception as exc:
                logger.exception("dsi_velocity_compute in-process failed job_id=%s", job_id)
                _dev_velocity_compute_results[task_id] = {
                    "state": "FAILURE",
                    "error": str(exc)[:800],
                }

        threading.Thread(
            target=_in_process,
            name=f"dsi-velocity-compute-{job_id}",
            daemon=True,
        ).start()
        _persist_velocity_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    out = _run_sync()
    _dev_velocity_compute_results[task_id] = {"state": "SUCCESS", "result": out}
    _persist_velocity_task_metadata(job_id, task_id, async_poll=False)
    return task_id, False


def _persist_velocity_task_metadata(job_id: int, task_id: str, *, async_poll: bool) -> None:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        job = db.get(ImportJob, int(job_id))
        if job is None:
            return
        meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
        meta["dsi_velocity_compute_task"] = to_jsonable(
            {
                "task_id": task_id,
                "async_poll": async_poll,
                "kind": "dsi_velocity_compute",
                "label": "Computing sell-out velocity…",
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        job.staged_metadata = to_jsonable(meta)
        db.add(job)
        db.commit()


def dispatch_dsi_velocity_after_apply(
    session: Session,
    job: ImportJob,
    distributor_id: int,
) -> None:
    task_id, async_poll = enqueue_dsi_velocity_compute(
        int(job.id),
        distributor_id=int(distributor_id),
        detach_from_caller=True,
    )
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["dsi_velocity_compute_task"] = to_jsonable(
        {
            "task_id": task_id,
            "async_poll": async_poll,
            "kind": "dsi_velocity_compute",
            "label": "Computing sell-out velocity…",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    job.staged_metadata = to_jsonable(meta)
    session.add(job)
    session.flush()
