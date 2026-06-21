"""Guardrails for concurrent DSI steward background tasks (plan apply, bulk provisional, pipeline)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.services.imports.import_job_background_metadata import (
    ACTIVE_CELERY_STATES,
    main_celery_task_id,
    read_main_celery_state,
)


def dsi_bulk_task_id(job: ImportJob) -> str | None:
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    bulk = meta.get("dsi_bulk_task")
    if not isinstance(bulk, dict):
        return None
    tid = bulk.get("task_id")
    if isinstance(tid, str) and tid.strip():
        return tid.strip()
    return None


def read_dsi_bulk_celery_state(job: ImportJob, *, timeout_s: float = 2.0) -> str | None:
    tid = dsi_bulk_task_id(job)
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


def steward_background_dispatch_conflict_message(job_id: int, *, reason: str) -> str:
    return f"DSI steward background work is already active for job {job_id} ({reason}). Wait for completion."


def _dsi_bulk_task_kind(job: ImportJob) -> str | None:
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    bulk = meta.get("dsi_bulk_task")
    if not isinstance(bulk, dict):
        return None
    kind = bulk.get("kind")
    return str(kind).strip() if isinstance(kind, str) and kind.strip() else None


def reusable_dsi_bulk_task_id(job: ImportJob, *, kind: str) -> str | None:
    """Return existing Celery task id when the same steward bulk kind is still in flight."""
    tid = dsi_bulk_task_id(job)
    if not tid:
        return None
    if _dsi_bulk_task_kind(job) != kind:
        return None
    state = read_dsi_bulk_celery_state(job)
    if state is not None and state in ACTIVE_CELERY_STATES:
        return tid
    return None


def assert_dsi_steward_background_dispatch_allowed(session: Session, job: ImportJob) -> None:
    """Raise ValueError when pipeline validate or another dsi_bulk_task is in flight."""
    if (job.status or "").strip().lower() == "running":
        state = read_main_celery_state(job)
        if state is not None and state in ACTIVE_CELERY_STATES:
            raise ValueError(
                steward_background_dispatch_conflict_message(int(job.id), reason="import validation running")
            )

    bulk_state = read_dsi_bulk_celery_state(job)
    if bulk_state is not None and bulk_state in ACTIVE_CELERY_STATES:
        meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        kind = "dsi_bulk_task"
        bulk = meta.get("dsi_bulk_task")
        if isinstance(bulk, dict) and bulk.get("kind"):
            kind = str(bulk.get("kind"))
        raise ValueError(
            steward_background_dispatch_conflict_message(int(job.id), reason=f"{kind} in progress")
        )
