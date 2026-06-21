"""Atomic import-pipeline dispatch claim (``imports.process_job``).

Prevents duplicate/concurrent validate/revalidate/process dispatches for the same job by
combining ``SELECT … FOR UPDATE``, Celery slot state, and a short-lived ``pipeline_queued_at``
claim window before the broker task id is persisted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob
from app.services.imports.import_background_slots import SLOT_MAIN, clear_task_slot_on_job
from app.services.imports.import_job_background_metadata import (
    ACTIVE_CELERY_STATES,
    TERMINAL_CELERY_STATES,
    persist_pipeline_queued_at,
    pipeline_dispatch_conflict_message,
    read_main_celery_state,
)
from app.utils.json_safe import to_jsonable

# DSI validate workers write ``dsi_validate_checkpoint_at`` on upfront sub-phases and row chunks.
# When the Celery result backend drops task state, a fresh checkpoint still proves a live worker.
FRESH_DSI_CHECKPOINT_SECONDS = 120

# After ``pipeline_queued_at`` is written and before ``celery_task_id`` is stored, block duplicates.
PIPELINE_DISPATCH_CLAIM_SECONDS = 120

_PIPELINE_CLAIM_META_KEY = "pipeline_dispatch_claim"


class PipelineDispatchBusyError(Exception):
    """Another pipeline dispatch is queued or running for this job."""

    def __init__(self, job_id: int) -> None:
        self.job_id = int(job_id)
        super().__init__(pipeline_dispatch_conflict_message(self.job_id))


def dsi_validate_checkpoint_age_seconds(job: ImportJob) -> float | None:
    """Seconds since the job's last durable DSI validate checkpoint, or None if absent."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = meta.get("dsi_validate_checkpoint_at")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def pipeline_queued_at_age_seconds(job: ImportJob) -> float | None:
    """Seconds since ``pipeline_queued_at``, or None if absent/unparseable."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = meta.get("pipeline_queued_at")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def import_pipeline_dispatch_is_busy(job: ImportJob) -> bool:
    """True when a ``process_job`` run is queued or in flight for this job (any job status)."""
    state = read_main_celery_state(job)
    if state is not None and state in ACTIVE_CELERY_STATES:
        return True
    if state is not None and state in TERMINAL_CELERY_STATES:
        return False

    queued_age = pipeline_queued_at_age_seconds(job)
    if queued_age is not None and queued_age < PIPELINE_DISPATCH_CLAIM_SECONDS:
        return True

    checkpoint_age = dsi_validate_checkpoint_age_seconds(job)
    if checkpoint_age is not None and checkpoint_age < FRESH_DSI_CHECKPOINT_SECONDS:
        return True

    return False


def reclaim_stale_pipeline_dispatch_claim(session: Session, job: ImportJob) -> bool:
    """Clear dead/terminal main-slot claims so dispatch is not blocked forever.

    Does nothing while the pipeline is still busy. Returns True when metadata was mutated.
    """
    if import_pipeline_dispatch_is_busy(job):
        return False

    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    had_claim = bool(
        meta.get("celery_task_id")
        or meta.get("pipeline_queued_at")
        or meta.get("pipeline_started_at")
        or meta.get(_PIPELINE_CLAIM_META_KEY)
    )
    if not had_claim:
        return False

    clear_task_slot_on_job(job, SLOT_MAIN)
    m2 = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    for key in ("pipeline_queued_at", "pipeline_started_at", _PIPELINE_CLAIM_META_KEY):
        m2.pop(key, None)
    job.staged_metadata = to_jsonable(m2) if m2 else None
    session.add(job)
    return True


def claim_import_pipeline_dispatch_sync(
    session: Session,
    job_id: int,
    *,
    import_mode: str | None = None,
) -> ImportJob:
    """Row-lock the job and record a new pipeline dispatch claim.

    Raises :class:`PipelineDispatchBusyError` when work is already queued/running.
    Raises ``ValueError('job_not_found')`` when the job id does not exist.
    """
    job = session.execute(
        select(ImportJob).where(ImportJob.id == int(job_id)).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("job_not_found")

    reclaim_stale_pipeline_dispatch_claim(session, job)

    if import_pipeline_dispatch_is_busy(job):
        raise PipelineDispatchBusyError(int(job_id))

    if import_mode is not None:
        job.import_mode = import_mode
    job.status = "running"
    job.error_summary = None
    job.completed_at = None
    persist_pipeline_queued_at(session, job)

    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta[_PIPELINE_CLAIM_META_KEY] = uuid.uuid4().hex
    job.staged_metadata = to_jsonable(meta)
    session.add(job)
    session.flush()
    return job


def claim_import_pipeline_dispatch(job_id: int, *, import_mode: str | None = None) -> ImportJob:
    """Open a sync session, atomically claim pipeline dispatch, and commit."""
    with SessionLocal() as session:
        try:
            job = claim_import_pipeline_dispatch_sync(session, job_id, import_mode=import_mode)
            session.commit()
            return job
        except PipelineDispatchBusyError:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail=pipeline_dispatch_conflict_message(int(job_id)),
            ) from None
        except ValueError as exc:
            session.rollback()
            if str(exc) == "job_not_found":
                raise HTTPException(status_code=404, detail="Import job not found") from exc
            raise
        except Exception:
            session.rollback()
            raise


def raise_if_import_pipeline_busy(job: ImportJob) -> None:
    """HTTP 409 when ``job`` already has queued/running pipeline work."""
    if import_pipeline_dispatch_is_busy(job):
        raise HTTPException(
            status_code=409,
            detail=pipeline_dispatch_conflict_message(int(job.id)),
        )
