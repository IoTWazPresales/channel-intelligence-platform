"""Clear Celery task refs from import_job.staged_metadata when work finishes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.utils.json_safe import to_jsonable

# Celery states that mean work is still in flight (show in global background UI).
ACTIVE_CELERY_STATES = frozenset({"PENDING", "STARTED", "PROGRESS"})

TERMINAL_CELERY_STATES = frozenset({"SUCCESS", "FAILURE", "REVOKED"})


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
