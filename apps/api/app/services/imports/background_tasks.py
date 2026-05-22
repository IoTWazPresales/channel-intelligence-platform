"""Discover import jobs with active Celery background work for global UI polling."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob
from app.services.imports.import_job_background_metadata import ACTIVE_CELERY_STATES
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _task_label(job: ImportJob, *, kind: str) -> str:
    jid = int(job.id)
    slug = (job.template_slug or "").strip()
    mode = (job.import_mode or "").strip().lower()
    if kind == "dsi_bulk_provisional":
        return f"Creating provisional customers (DSI job {jid})"
    if slug == "distributor_inventory":
        if mode == "validate":
            return f"Validating DSI import {jid}"
        return f"Processing DSI import {jid}"
    if slug == "inbound_shipments":
        return f"Processing shipment import {jid}"
    if slug == "product_master":
        return f"Applying product master (job {jid})"
    return f"Import job {jid}"


def _read_celery(task_id: str) -> tuple[str, dict[str, Any]]:
    from celery.result import AsyncResult

    r = AsyncResult(task_id, app=celery_app)
    state = str(r.state or "PENDING")
    info = r.info if isinstance(r.info, dict) else {}
    return state, info


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
            if isinstance(btid, str) and btid.strip():
                descriptors.append(
                    ("bulk", btid.strip(), "dsi_bulk_provisional", _task_label(job, kind="dsi_bulk_provisional"))
                )

        if not descriptors:
            continue

        for slot, task_id, kind, label in descriptors:
            task_state = "PENDING"
            info: dict[str, Any] = {}
            try:
                task_state, info = _read_celery(task_id)
            except Exception as exc:
                logger.debug("background_tasks: celery read failed job=%s task=%s: %s", job.id, task_id, exc)

            if task_state not in ACTIVE_CELERY_STATES:
                if slot == "main":
                    meta.pop("celery_task_id", None)
                else:
                    meta.pop("dsi_bulk_task", None)
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


async def list_active_import_background_tasks(*, limit: int = 40) -> list[dict[str, Any]]:
    return await asyncio.to_thread(list_active_import_background_tasks_sync, limit=limit)
