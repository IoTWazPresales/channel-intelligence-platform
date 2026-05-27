"""Enqueue DSI SOH reconciliation after apply completes."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion import ImportJob
from app.services.imports.dsi_soh_reconciliation_sync import run_dsi_soh_reconciliation_sync
from app.utils.json_safe import to_jsonable
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
        _persist_soh_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    settings = get_settings()
    use_thread = detach_from_caller or settings.cip_dev_celery_dispatch == "in_process_thread"
    task_id = f"dev-soh-reconcile-{uuid.uuid4().hex}"

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

        threading.Thread(
            target=_in_process,
            name=f"dsi-soh-reconcile-{job_id}",
            daemon=True,
        ).start()
        _persist_soh_task_metadata(job_id, task_id, async_poll=True)
        return task_id, True

    out = _run_sync()
    _dev_soh_reconcile_results[task_id] = {"state": "SUCCESS", "result": out}
    _persist_soh_task_metadata(job_id, task_id, async_poll=False)
    return task_id, False


def _persist_soh_task_metadata(job_id: int, task_id: str, *, async_poll: bool) -> None:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        job = db.get(ImportJob, int(job_id))
        if job is None:
            return
        meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
        meta["dsi_soh_reconcile_task"] = to_jsonable(
            {
                "task_id": task_id,
                "async_poll": async_poll,
                "kind": "dsi_soh_reconciliation",
                "label": "Reconciling inventory…",
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        job.staged_metadata = to_jsonable(meta)
        db.add(job)
        db.commit()


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
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["dsi_soh_reconcile_task"] = to_jsonable(
        {
            "task_id": task_id,
            "async_poll": async_poll,
            "kind": "dsi_soh_reconciliation",
            "label": "Reconciling inventory…",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    job.staged_metadata = to_jsonable(meta)
    session.add(job)
    session.flush()
