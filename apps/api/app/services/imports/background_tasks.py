"""Discover import jobs with active Celery background work for global UI polling."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob
from app.services.imports.import_background_slots import (
    SLOT_MAIN,
    SLOT_PM_COMMIT,
    clear_task_slot,
    iter_active_slots,
    jobs_with_possible_background_tasks,
)
from app.services.imports.import_background_slots import task_label as _task_label
from app.services.imports.import_job_background_metadata import (
    ACTIVE_CELERY_STATES,
    TERMINAL_CELERY_STATES,
    job_db_indicates_pipeline_finished,
)
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

STALE_PENDING_SLOT_AGE = timedelta(minutes=20)


def _normalize_celery_state(state: str | None) -> str:
    return (state or "PENDING").strip().upper()


def _read_celery(task_id: str) -> tuple[str, dict[str, Any]]:
    from celery.result import AsyncResult

    r = AsyncResult(task_id, app=celery_app)
    state = _normalize_celery_state(str(r.state or "PENDING"))
    info = r.info if isinstance(r.info, dict) else {}
    return state, info


def read_celery_with_timeout(task_id: str, *, timeout_s: float = 3.0) -> tuple[str, dict[str, Any]]:
    """Read Celery result backend with a hard timeout (avoids blocking the API event loop)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_read_celery, task_id)
        try:
            return fut.result(timeout=timeout_s)
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"Celery read timed out for task {task_id}") from exc


def _read_celery_safe(task_id: str, *, timeout_s: float = 3.0) -> tuple[str, dict[str, Any]]:
    try:
        return read_celery_with_timeout(task_id, timeout_s=timeout_s)
    except TimeoutError:
        logger.warning("background_tasks: celery read timed out task=%s", task_id)
        return "PENDING", {}
    except Exception as exc:
        logger.debug("background_tasks: celery read failed task=%s: %s", task_id, exc)
        return "PENDING", {}


def _job_db_indicates_background_work_finished(job: ImportJob) -> bool:
    return job_db_indicates_pipeline_finished(job)


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _slot_dispatch_time(job: ImportJob, task_id: str) -> datetime | None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    for val in meta.values():
        if isinstance(val, dict) and str(val.get("task_id") or "") == task_id:
            dt = _parse_iso_datetime(val.get("queued_at"))
            if dt is not None:
                return dt
    dt = _parse_iso_datetime(meta.get("pipeline_queued_at"))
    if dt is not None:
        return dt
    updated = getattr(job, "updated_at", None)
    if updated is not None:
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return updated
    return None


def _clear_slot_when_pipeline_finished(job: ImportJob, slot_key: str) -> bool:
    """Only pipeline-bound slots clear when job stage indicates that pipeline finished.

    Steward bulk tasks (plan compute/apply on validated DSI jobs) stay visible until
    Celery reports a terminal state.
    """
    if slot_key == SLOT_MAIN:
        return _job_db_indicates_background_work_finished(job)
    if slot_key == SLOT_PM_COMMIT:
        return (job.stage or "").strip().lower() == "pm_committed"
    return False


def _celery_pending_stale(job: ImportJob, task_id: str, task_state: str, info: dict[str, Any]) -> bool:
    """True when Celery still reports PENDING with no progress long after dispatch."""
    if task_state != "PENDING" or info:
        return False
    dispatch = _slot_dispatch_time(job, task_id)
    if dispatch is None:
        return False
    return (datetime.now(timezone.utc) - dispatch) >= STALE_PENDING_SLOT_AGE


def _steward_bulk_candidate_count(meta: dict[str, Any]) -> int:
    bulk = meta.get("dsi_bulk_task")
    if not isinstance(bulk, dict):
        return 0
    raw = bulk.get("candidate_count")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _progress_from_celery(
    *,
    task_state: str,
    info: dict[str, Any],
    job: ImportJob,
) -> dict[str, Any]:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    steward_total = _steward_bulk_candidate_count(meta)
    total_rows = int(
        info.get("total_rows") or steward_total or meta.get("dsi_validate_total_rows") or 0
    )
    current_row = int(info.get("current_row") or 0)
    pct = int(info.get("pct") or 0)
    phase = str(info.get("phase") or "processing")
    phase_label = str(info.get("phase_label") or "Working…")
    if task_state in ("PENDING", "STARTED") and not info:
        phase, phase_label = "queued", "Queued"
    return {
        "phase": phase,
        "phase_label": phase_label,
        "current_row": current_row,
        "total_rows": total_rows,
        "pct": pct,
        "task_state": task_state,
    }


def list_active_import_background_tasks_sync(*, limit: int = 40) -> list[dict[str, Any]]:
    """Return in-flight Celery tasks only; clear stale refs when Celery reports terminal state."""
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(ImportJob)
                .where(ImportJob.archived_at.is_(None))
                .where(jobs_with_possible_background_tasks())
                .order_by(ImportJob.id.desc())
                .limit(limit)
            ).all()
        )

        out, dirty = _build_background_task_records(session, rows)
        if dirty:
            session.commit()
        return out


def _build_background_task_records(
    session,
    rows: list[ImportJob],
) -> tuple[list[dict[str, Any]], bool]:
    out: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    dirty = False

    for job in rows:
        meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
        slots = list(iter_active_slots(job))
        if not slots:
            continue

        for slot in slots:
            if _clear_slot_when_pipeline_finished(job, slot.slot_key):
                clear_task_slot(meta, slot.slot_key)
                job.staged_metadata = to_jsonable(meta) if meta else None
                session.add(job)
                dirty = True
                continue

            task_state, info = _read_celery_safe(slot.task_id)

            if _celery_pending_stale(job, slot.task_id, task_state, info):
                clear_task_slot(meta, slot.slot_key)
                job.staged_metadata = to_jsonable(meta) if meta else None
                session.add(job)
                dirty = True
                continue

            if task_state in TERMINAL_CELERY_STATES or task_state not in ACTIVE_CELERY_STATES:
                clear_task_slot(meta, slot.slot_key)
                job.staged_metadata = to_jsonable(meta) if meta else None
                session.add(job)
                dirty = True
                continue

            progress = _progress_from_celery(task_state=task_state, info=info, job=job)
            out.append(
                {
                    "task_id": slot.task_id,
                    "import_job_id": int(job.id),
                    "kind": slot.kind,
                    "label": slot.label,
                    "status": "running",
                    "template_slug": job.template_slug,
                    "file_name": job.file_name,
                    "polled_at": now,
                    **progress,
                }
            )

    return out, dirty


def list_recent_failed_import_background_tasks_sync(*, limit: int = 10) -> list[dict[str, Any]]:
    """Recent failed jobs for global indicator retry affordance (no active Celery task)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
    now = datetime.now(timezone.utc).isoformat()
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(ImportJob)
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status == "failed")
                .where(ImportJob.updated_at >= cutoff)
                .order_by(ImportJob.id.desc())
                .limit(limit)
            ).all()
        )
        out: list[dict[str, Any]] = []
        for job in rows:
            meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
            if meta.get("celery_task_id") or meta.get("dsi_bulk_task"):
                continue
            kind = "dsi_pipeline"
            if (job.template_slug or "") == "inbound_shipments":
                kind = "shipment_import"
            elif (job.template_slug or "") == "product_master":
                kind = "product_master_commit"
            out.append(
                {
                    "task_id": f"failed-job-{job.id}",
                    "import_job_id": int(job.id),
                    "kind": kind,
                    "label": _task_label(job, kind=kind),
                    "status": "failed",
                    "template_slug": job.template_slug,
                    "file_name": job.file_name,
                    "phase": "failed",
                    "phase_label": (job.error_summary or "Failed")[:120],
                    "current_row": 0,
                    "total_rows": 0,
                    "pct": 0,
                    "task_state": "FAILURE",
                    "polled_at": now,
                    "can_retry": True,
                }
            )
        return out


async def list_active_import_background_tasks(*, limit: int = 40) -> list[dict[str, Any]]:
    return await asyncio.to_thread(list_active_import_background_tasks_sync, limit=limit)


async def list_import_background_tasks_for_ui(*, limit: int = 40, failed_limit: int = 10) -> dict[str, Any]:
    active = await list_active_import_background_tasks(limit=limit)
    failed = await asyncio.to_thread(list_recent_failed_import_background_tasks_sync, limit=failed_limit)
    active_ids = {t["import_job_id"] for t in active}
    failed_deduped = [t for t in failed if t["import_job_id"] not in active_ids]
    tasks = active + failed_deduped
    return {"tasks": tasks, "count": len(tasks), "active_count": len(active)}
