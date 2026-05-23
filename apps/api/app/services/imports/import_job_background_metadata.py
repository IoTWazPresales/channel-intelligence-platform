"""Clear Celery task refs from import_job.staged_metadata when work finishes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.utils.json_safe import to_jsonable

# Celery states that mean work is still in flight (show in global background UI).
ACTIVE_CELERY_STATES = frozenset({"PENDING", "STARTED", "PROGRESS"})

TERMINAL_CELERY_STATES = frozenset({"SUCCESS", "FAILURE", "REVOKED"})


def job_db_indicates_pipeline_finished(job: ImportJob) -> bool:
    """True when import pipeline work is done in DB (not actively re-running).

    ``status=running`` always means in-flight — even if ``stage`` is still ``validated``
    between revalidate dispatch and worker stage updates.
    """
    status = (job.status or "").strip().lower()
    if status == "running":
        return False
    stage = (job.stage or "").strip().lower()
    if stage in ("validated", "loaded", "failed"):
        return True
    return status in ("completed", "completed_with_errors", "failed")


def main_celery_task_id(job: ImportJob) -> str | None:
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    tid = meta.get("celery_task_id")
    if isinstance(tid, str) and tid.strip():
        return tid.strip()
    return None


def read_main_celery_state(job: ImportJob, *, timeout_s: float = 2.0) -> str | None:
    """Return normalized Celery state for the job's main task, or None if no task id."""
    tid = main_celery_task_id(job)
    if not tid:
        return None
    from app.services.imports.background_tasks import read_celery_with_timeout

    try:
        state, _info = read_celery_with_timeout(tid, timeout_s=timeout_s)
        return state
    except TimeoutError:
        return "PENDING"
    except Exception:
        return None


def pipeline_dispatch_conflict_message(job_id: int) -> str:
    return f"Import validation is already running for job {job_id}. Wait for completion or cancel the job."


def clear_background_task_metadata(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return staged_metadata without background-task keys (or None if empty)."""
    if not isinstance(meta, dict):
        return None
    m = dict(meta)
    m.pop("celery_task_id", None)
    m.pop("dsi_bulk_task", None)
    return to_jsonable(m) if m else None


def clear_background_task_metadata_on_job(job: ImportJob) -> bool:
    """Remove celery_task_id / dsi_bulk_task from job. Returns True if mutated."""
    if not isinstance(job.staged_metadata, dict):
        return False
    if "celery_task_id" not in job.staged_metadata and "dsi_bulk_task" not in job.staged_metadata:
        return False
    job.staged_metadata = clear_background_task_metadata(job.staged_metadata)
    return True


def persist_clear_background_task_metadata(session: Session, job: ImportJob) -> None:
    if clear_background_task_metadata_on_job(job):
        session.add(job)
