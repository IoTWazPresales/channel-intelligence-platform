"""Cancel and retry import jobs with Celery background work."""

from __future__ import annotations

import logging
from typing import Any

from celery.result import AsyncResult
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.services.imports.import_job_background_metadata import clear_background_task_metadata_on_job
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _collect_celery_task_ids(meta: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    main = meta.get("celery_task_id")
    if isinstance(main, str) and main.strip():
        ids.append(main.strip())
    bulk = meta.get("dsi_bulk_task")
    if isinstance(bulk, dict):
        bt = bulk.get("task_id")
        if isinstance(bt, str) and bt.strip():
            ids.append(bt.strip())
    return ids


def _revoke_celery_tasks(task_ids: list[str]) -> None:
    for task_id in task_ids:
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
            AsyncResult(task_id, app=celery_app).revoke(terminate=True, signal="SIGTERM")
        except Exception as exc:
            logger.debug("revoke failed task_id=%s: %s", task_id, exc)


def cancel_import_job_sync(session: Session, job_id: int) -> dict[str, Any]:
    """Revoke in-flight Celery work, clear metadata, mark job failed (including stale queued refs)."""
    job = session.get(ImportJob, job_id)
    if job is None:
        raise ValueError("job_not_found")

    previous_status = str(job.status or "")
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    task_ids = _collect_celery_task_ids(meta)
    if task_ids:
        _revoke_celery_tasks(task_ids)

    clear_background_task_metadata_on_job(job)
    job.status = "failed"
    job.error_summary = "Cancelled by user"
    job.stage = "failed"
    session.add(job)
    session.commit()
    session.refresh(job)

    return {
        "cancelled": True,
        "job_id": int(job.id),
        "previous_status": previous_status,
    }


def prepare_import_job_retry_sync(session: Session, job_id: int) -> ImportJob:
    """Reset a failed job for re-dispatch; caller enqueues Celery and stores task id."""
    job = session.get(ImportJob, job_id)
    if job is None:
        raise ValueError("job_not_found")
    if str(job.status or "").strip() != "failed":
        raise ValueError("job_not_failed")

    clear_background_task_metadata_on_job(job)
    job.status = "pending"
    job.error_summary = None
    slug = (job.template_slug or "").strip()
    if slug == "distributor_inventory":
        job.stage = "dsi_mapping_ready"
    elif slug == "inbound_shipments":
        job.stage = "shipment_mapping_ready"
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
