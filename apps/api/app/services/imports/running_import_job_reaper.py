"""Periodic reaper for import jobs stuck in ``status=running`` after Celery work died.

Uses ``celery.control.inspect().active()`` only — never terminates DB sessions or
connections. When inspect is unavailable, does nothing (fail-safe).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_FAILED
from app.models.ingestion import ImportJob
from app.services.imports.background_tasks import _parse_iso_datetime
from app.services.imports.import_background_slots import SLOT_MAIN, clear_task_slot
from app.services.imports.import_job_background_metadata import main_celery_task_id
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_DEV_IN_PROCESS_TASK_ID = "dev-in-process-thread"
_DEFAULT_BEAT_INTERVAL_S = 120
_DEFAULT_CHECKPOINT_STALE_MINUTES = 5
_DEFAULT_DISPATCH_GRACE_MINUTES = 2
_DEFAULT_INSPECT_TIMEOUT_S = 3.0


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def checkpoint_stale_age() -> timedelta:
    return timedelta(minutes=_env_int("CIP_RUNNING_JOB_REAPER_CHECKPOINT_STALE_MINUTES", _DEFAULT_CHECKPOINT_STALE_MINUTES))


def dispatch_grace_age() -> timedelta:
    return timedelta(minutes=_env_int("CIP_RUNNING_JOB_REAPER_DISPATCH_GRACE_MINUTES", _DEFAULT_DISPATCH_GRACE_MINUTES))


def collect_active_celery_task_ids(*, timeout_s: float = _DEFAULT_INSPECT_TIMEOUT_S) -> set[str] | None:
    """Active task ids from all workers, or ``None`` when inspect did not respond."""
    try:
        inspector = celery_app.control.inspect(timeout=timeout_s)
        active_by_worker = inspector.active()
    except Exception as exc:
        logger.warning("running_import_job_reaper: celery inspect failed: %s", exc)
        return None
    if active_by_worker is None:
        logger.warning("running_import_job_reaper: celery inspect returned no workers")
        return None
    out: set[str] = set()
    for tasks in active_by_worker.values():
        if not tasks:
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            tid = task.get("id")
            if isinstance(tid, str) and tid.strip():
                out.add(tid.strip())
    return out


def _pipeline_dispatch_time(meta: dict[str, Any]) -> datetime | None:
    return _parse_iso_datetime(meta.get("pipeline_queued_at")) or _parse_iso_datetime(
        meta.get("pipeline_started_at")
    )


def _dsi_checkpoint_time(meta: dict[str, Any]) -> datetime | None:
    return _parse_iso_datetime(meta.get("dsi_validate_checkpoint_at"))


def _is_reap_candidate(
    *,
    task_id: str,
    active_ids: set[str],
    meta: dict[str, Any],
    now: datetime,
) -> tuple[bool, str]:
    """Return (should_mark_failed, reason) — only when Celery confirms task is not active."""
    if task_id in active_ids:
        return False, ""

    dispatch_at = _pipeline_dispatch_time(meta)
    if dispatch_at is not None and (now - dispatch_at) < dispatch_grace_age():
        return False, ""

    checkpoint_at = _dsi_checkpoint_time(meta)
    checkpoint_stale = checkpoint_at is None or (now - checkpoint_at) >= checkpoint_stale_age()

    if checkpoint_stale:
        if checkpoint_at is None:
            detail = "no DSI validate checkpoint"
        else:
            detail = f"last checkpoint {checkpoint_at.isoformat()}"
        return True, (
            "Import worker is not running this task (Celery inspect/active) and validation "
            f"progress is stale ({detail}). Re-dispatch validation or cancel and retry."
        )

    return True, (
        "Import worker is not running this task (Celery inspect/active). "
        "The background task may have exited without updating the job. Re-dispatch or retry."
    )


def reap_stale_running_import_jobs_sync() -> dict[str, Any]:
    """Mark stuck ``running`` jobs failed when Celery confirms their task is not active."""
    active_ids = collect_active_celery_task_ids()
    if active_ids is None:
        return {"inspected": False, "scanned": 0, "marked_failed": 0, "job_ids": []}

    now = datetime.now(timezone.utc)
    marked: list[int] = []

    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(ImportJob)
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status == "running")
                .order_by(ImportJob.id.asc())
            ).all()
        )

        for job in rows:
            task_id = main_celery_task_id(job)
            if not task_id or task_id == _DEV_IN_PROCESS_TASK_ID:
                continue

            meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
            should_mark, reason = _is_reap_candidate(
                task_id=task_id,
                active_ids=active_ids,
                meta=meta,
                now=now,
            )
            if not should_mark:
                continue

            clear_task_slot(meta, SLOT_MAIN)
            job.staged_metadata = to_jsonable(meta) if meta else None
            job.status = "failed"
            job.stage = STAGE_FAILED
            job.error_summary = reason[:500]
            job.completed_at = now
            session.add(job)
            marked.append(int(job.id))
            logger.info(
                "running_import_job_reaper: marked job_id=%s failed task_id=%s",
                job.id,
                task_id,
            )

        if marked:
            session.commit()
        else:
            session.rollback()

    return {
        "inspected": True,
        "scanned": len(rows),
        "marked_failed": len(marked),
        "job_ids": marked,
    }
