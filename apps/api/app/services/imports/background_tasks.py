"""Discover import jobs with active Celery background work for global UI polling."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob
from app.services.imports.import_job_background_metadata import (
    ACTIVE_CELERY_STATES,
    TERMINAL_CELERY_STATES,
    job_db_indicates_pipeline_finished,
)
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _task_label(job: ImportJob, *, kind: str) -> str:
    jid = int(job.id)
    slug = (job.template_slug or "").strip()
    mode = (job.import_mode or "").strip().lower()
    if kind == "dsi_bulk_provisional":
        return f"Creating provisional customers (DSI job {jid})"
    if kind == "dsi_resolution_plan_apply":
        return f"Applying resolution plan (DSI job {jid})"
    if kind == "dsi_soh_reconciliation":
        return f"Reconciling inventory (DSI job {jid})"
    if kind == "dsi_velocity_compute":
        return f"Computing sell-out velocity (DSI job {jid})"
    if kind == "dsi_forecasting":
        return f"Generating forecasts (DSI job {jid})"
    if kind == "product_master_validate":
        return f"Validating product master (job {jid})"
    if kind == "commercial_planner_lineup_parse":
        return f"Parsing current lineup (job {jid})"
    if slug == "distributor_inventory":
        if mode == "validate":
            return f"Validating DSI import {jid}"
        return f"Processing DSI import {jid}"
    if slug == "inbound_shipments":
        return f"Processing shipment import {jid}"
    if slug == "product_master":
        return f"Applying product master (job {jid})"
    return f"Import job {jid}"


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


def _clear_task_slot_metadata(meta: dict[str, Any], slot: str) -> None:
    if slot == "main":
        meta.pop("celery_task_id", None)
    elif slot == "soh":
        meta.pop("dsi_soh_reconcile_task", None)
    elif slot == "velocity":
        meta.pop("dsi_velocity_compute_task", None)
    elif slot == "forecasting":
        meta.pop("dsi_forecasting_task", None)
    elif slot == "pm_validate":
        meta.pop("pm_validate_task", None)
    elif slot == "pm_commit":
        meta.pop("pm_commit_task", None)
    elif slot == "lineup_parse":
        meta.pop("lineup_parse_task", None)
    else:
        meta.pop("dsi_bulk_task", None)


def _progress_from_celery(
    *,
    task_state: str,
    info: dict[str, Any],
    job: ImportJob,
) -> dict[str, Any]:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    total_rows = int(info.get("total_rows") or meta.get("dsi_validate_total_rows") or 0)
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


def _jobs_with_possible_background_tasks():
    """Narrow scan: running jobs or staged_metadata that still references a Celery task."""
    has_meta = ImportJob.staged_metadata.isnot(None)
    return or_(
        ImportJob.status == "running",
        and_(has_meta, ImportJob.staged_metadata.has_key("celery_task_id")),
        and_(has_meta, ImportJob.staged_metadata.has_key("dsi_bulk_task")),
        and_(has_meta, ImportJob.staged_metadata.has_key("lineup_parse_task")),
        and_(has_meta, ImportJob.staged_metadata.has_key("pm_validate_task")),
        and_(has_meta, ImportJob.staged_metadata.has_key("pm_commit_task")),
    )


def list_active_import_background_tasks_sync(*, limit: int = 40) -> list[dict[str, Any]]:
    """Return in-flight Celery tasks only; clear stale refs when Celery reports terminal state."""
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(ImportJob)
                .where(ImportJob.archived_at.is_(None))
                .where(_jobs_with_possible_background_tasks())
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
        descriptors: list[tuple[str, str, str, str]] = []

        main_tid = meta.get("celery_task_id")
        if isinstance(main_tid, str) and main_tid.strip():
            kind = "dsi_pipeline"
            if (job.template_slug or "") == "inbound_shipments":
                kind = "shipment_import"
            elif (job.template_slug or "") == "product_master":
                kind = "product_master_commit"
            descriptors.append(("main", main_tid.strip(), kind, _task_label(job, kind=kind)))

        bulk = meta.get("dsi_bulk_task")
        if isinstance(bulk, dict):
            btid = bulk.get("task_id")
            bulk_kind = bulk.get("kind")
            if isinstance(btid, str) and btid.strip():
                kind_key = (
                    str(bulk_kind).strip()
                    if isinstance(bulk_kind, str) and bulk_kind.strip()
                    else "dsi_bulk_provisional"
                )
                if kind_key not in ("dsi_bulk_provisional", "dsi_resolution_plan_apply"):
                    kind_key = "dsi_bulk_provisional"
                descriptors.append(
                    ("bulk", btid.strip(), kind_key, _task_label(job, kind=kind_key))
                )

        soh_task = meta.get("dsi_soh_reconcile_task")
        if isinstance(soh_task, dict):
            stid = soh_task.get("task_id")
            if isinstance(stid, str) and stid.strip():
                descriptors.append(
                    (
                        "soh",
                        stid.strip(),
                        "dsi_soh_reconciliation",
                        str(soh_task.get("label") or "Reconciling inventory…"),
                    )
                )

        velocity_task = meta.get("dsi_velocity_compute_task")
        if isinstance(velocity_task, dict):
            vtid = velocity_task.get("task_id")
            if isinstance(vtid, str) and vtid.strip():
                descriptors.append(
                    (
                        "velocity",
                        vtid.strip(),
                        "dsi_velocity_compute",
                        str(velocity_task.get("label") or "Computing sell-out velocity…"),
                    )
                )

        forecasting_task = meta.get("dsi_forecasting_task")
        if isinstance(forecasting_task, dict):
            ftid = forecasting_task.get("task_id")
            if isinstance(ftid, str) and ftid.strip():
                descriptors.append(
                    (
                        "forecasting",
                        ftid.strip(),
                        "dsi_forecasting",
                        str(forecasting_task.get("label") or "Generating forecasts…"),
                    )
                )

        pm_validate_task = meta.get("pm_validate_task")
        if isinstance(pm_validate_task, dict):
            ptid = pm_validate_task.get("task_id")
            if isinstance(ptid, str) and ptid.strip():
                descriptors.append(
                    (
                        "pm_validate",
                        ptid.strip(),
                        "product_master_validate",
                        str(pm_validate_task.get("label") or "Validating product master…"),
                    )
                )

        pm_commit_task = meta.get("pm_commit_task")
        if isinstance(pm_commit_task, dict):
            ctid = pm_commit_task.get("task_id")
            if isinstance(ctid, str) and ctid.strip():
                descriptors.append(
                    (
                        "pm_commit",
                        ctid.strip(),
                        "product_master_commit",
                        str(pm_commit_task.get("label") or "Committing product master…"),
                    )
                )

        lineup_parse_task = meta.get("lineup_parse_task")
        if isinstance(lineup_parse_task, dict):
            ltid = lineup_parse_task.get("task_id")
            if isinstance(ltid, str) and ltid.strip():
                descriptors.append(
                    (
                        "lineup_parse",
                        ltid.strip(),
                        "commercial_planner_lineup_parse",
                        str(lineup_parse_task.get("label") or "Parsing current lineup…"),
                    )
                )

        if not descriptors:
            continue

        for slot, task_id, kind, label in descriptors:
            if _job_db_indicates_background_work_finished(job):
                _clear_task_slot_metadata(meta, slot)
                job.staged_metadata = to_jsonable(meta) if meta else None
                session.add(job)
                dirty = True
                continue

            task_state = "PENDING"
            info: dict[str, Any] = {}
            task_state, info = _read_celery_safe(task_id)

            if task_state in TERMINAL_CELERY_STATES:
                _clear_task_slot_metadata(meta, slot)
                job.staged_metadata = to_jsonable(meta) if meta else None
                session.add(job)
                dirty = True
                continue

            if task_state not in ACTIVE_CELERY_STATES:
                _clear_task_slot_metadata(meta, slot)
                job.staged_metadata = to_jsonable(meta) if meta else None
                session.add(job)
                dirty = True
                continue

            progress = _progress_from_celery(task_state=task_state, info=info, job=job)
            out.append(
                {
                    "task_id": task_id,
                    "import_job_id": int(job.id),
                    "kind": kind,
                    "label": label,
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
