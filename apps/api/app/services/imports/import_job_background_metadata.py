"""Clear Celery task refs from import_job.staged_metadata when work finishes."""

from __future__ import annotations

from datetime import datetime, timezone
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
    if stage in ("validated", "loaded", "failed", "pm_committed"):
        return True
    return status in ("completed", "completed_with_errors", "failed", "commit_failed")


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


def persist_pipeline_queued_at(session: Session, job: ImportJob) -> None:
    """Record HTTP dispatch time before the worker picks up the Celery task."""
    m = dict(job.staged_metadata or {})
    now = datetime.now(timezone.utc).isoformat()
    m["pipeline_queued_at"] = now
    m.pop("pipeline_started_at", None)
    job.staged_metadata = to_jsonable(m)
    session.add(job)


def persist_pipeline_worker_started_at(session: Session, job: ImportJob) -> None:
    """Record first worker execution (once per dispatch)."""
    m = dict(job.staged_metadata or {})
    if m.get("pipeline_started_at"):
        return
    m["pipeline_started_at"] = datetime.now(timezone.utc).isoformat()
    job.staged_metadata = to_jsonable(m)
    session.add(job)


def clear_background_task_metadata(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return staged_metadata without ANY background-task slot (or None if empty).

    Clears every registered slot (not just ``celery_task_id`` / ``dsi_bulk_task``) plus
    the pipeline timing keys, so cancel/retry can never leave an orphan ``pm_commit_task``,
    ``pm_validate_task``, ``dsi_soh_reconcile_task``, ``dsi_velocity_compute_task``,
    ``dsi_forecasting_task`` or ``lineup_parse_task`` that the activity feed keeps showing.
    """
    from app.services.imports.import_background_slots import clear_all_task_slots

    return clear_all_task_slots(meta, include_timing=True)


def clear_background_task_metadata_on_job(job: ImportJob) -> bool:
    """Remove every background-task slot from the job. Returns True if mutated."""
    from app.services.imports.import_background_slots import has_any_task_slot

    if not isinstance(job.staged_metadata, dict):
        return False
    meta = job.staged_metadata
    if not has_any_task_slot(meta) and "pipeline_queued_at" not in meta and "pipeline_started_at" not in meta:
        return False
    job.staged_metadata = clear_background_task_metadata(meta)
    return True


def persist_clear_background_task_metadata(session: Session, job: ImportJob) -> None:
    if clear_background_task_metadata_on_job(job):
        session.add(job)
