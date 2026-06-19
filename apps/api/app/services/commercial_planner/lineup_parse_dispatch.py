"""Enqueue current lineup case parse to Celery (or dev in-process thread)."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.services.commercial_planner.current_lineup_seed import ensure_current_lineup_import_seed_sync
from app.services.commercial_planner.lineup_parse_worker import (
    ASYNC_PARSE_BYTE_THRESHOLD,
    ASYNC_PARSE_ROW_THRESHOLD,
)
from app.services.imports.import_background_slots import SLOT_LINEUP_PARSE, set_task_slot_on_job
from app.services.task_run_ledger import (
    ENTITY_IMPORT_JOB,
    TRANSPORT_BROKER,
    TRANSPORT_IN_PROCESS_THREAD,
    create_queued_task_run,
    spawn_in_process_thread_with_ledger,
)

logger = logging.getLogger(__name__)
DEV_CELERY_LOGGER = logging.getLogger("cip.dev_celery")


def should_parse_lineup_async(*, file_bytes: bytes, preview_total_rows: int | None = None) -> bool:
    if len(file_bytes) >= ASYNC_PARSE_BYTE_THRESHOLD:
        return True
    if preview_total_rows is not None and preview_total_rows >= ASYNC_PARSE_ROW_THRESHOLD:
        return True
    return False


def _persist_lineup_parse_task_metadata(
    job: ImportJob,
    *,
    task_id: str,
    case_id: int,
    filename: str,
) -> None:
    set_task_slot_on_job(
        job,
        SLOT_LINEUP_PARSE,
        task_id=task_id,
        case_id=case_id,
        filename=filename,
        label=f"Parsing lineup case #{case_id}…",
    )


def prepare_lineup_parse_import_job_sync(
    session: Session,
    *,
    case_id: int,
    filename: str,
) -> ImportJob:
    """Create a running ImportJob audit row for an async lineup parse."""
    case = session.get(CommercialLineupCase, case_id)
    if case is None:
        raise ValueError(f"Lineup case {case_id} not found")

    ensure_current_lineup_import_seed_sync(session.connection())
    source = session.scalar(
        select(SourceDefinition)
        .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
        .where(ImportTemplate.slug == "current_lineup", SourceDefinition.code == "current_lineup_system")
        .limit(1)
    )
    if source is None:
        raise ValueError("current_lineup_system source is not configured")

    now = datetime.now(timezone.utc)
    job = ImportJob(
        source_id=source.id,
        template_slug="current_lineup",
        import_mode="apply",
        status="running",
        file_name=filename,
        started_at=now,
    )
    session.add(job)
    session.flush()
    return job


def enqueue_lineup_parse_sync(
    *,
    case_id: int,
    filename: str,
    file_bytes: bytes,
    import_job_id: int,
) -> dict[str, Any]:
    """Dispatch lineup parse to Celery; returns outcome dict for HTTP layer."""
    settings = get_settings()
    file_b64 = base64.standard_b64encode(file_bytes).decode("ascii")
    celery_task_id: str | None = None
    task_name = "commercial_planner.parse_lineup_case"

    def _run_sync() -> None:
        from app.services.commercial_planner.lineup_parse_worker import run_lineup_case_parse_job

        run_lineup_case_parse_job(
            case_id,
            filename,
            file_b64,
            import_job_id=import_job_id,
            celery_task_id=celery_task_id,
        )

    if settings.cip_dev_celery_dispatch == "in_process_thread":
        DEV_CELERY_LOGGER.warning(
            "ENQUEUE: lineup parse case_id=%s — in_process_thread (DEV ONLY).",
            case_id,
        )
        celery_task_id = "dev-in-process-thread"
        create_queued_task_run(
            task_run_id=celery_task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=import_job_id,
            transport=TRANSPORT_IN_PROCESS_THREAD,
        )
        spawn_in_process_thread_with_ledger(
            task_run_id=celery_task_id,
            thread_name=f"lineup-parse-{case_id}",
            target=_run_sync,
        )
    else:
        from app.worker.tasks import commercial_planner_lineup_parse_task

        try:
            async_result = commercial_planner_lineup_parse_task.delay(
                case_id,
                filename,
                file_b64,
                import_job_id,
            )
            celery_task_id = str(async_result.id)
            create_queued_task_run(
                task_run_id=celery_task_id,
                task_name=task_name,
                entity_type=ENTITY_IMPORT_JOB,
                entity_id=import_job_id,
                transport=TRANSPORT_BROKER,
            )
        except Exception as exc:
            logger.exception("lineup parse dispatch failed case_id=%s", case_id)
            with SessionLocal() as session:
                job = session.get(ImportJob, import_job_id)
                if job is not None:
                    job.status = "failed"
                    job.error_summary = "Lineup parse could not be dispatched to the worker."
                    job.completed_at = datetime.now(timezone.utc)
                    session.commit()
            return {
                "outcome": "dispatch_failed",
                "http_status": 503,
                "message": str(exc),
            }

    if celery_task_id:
        with SessionLocal() as session:
            job = session.get(ImportJob, import_job_id)
            if job is not None:
                _persist_lineup_parse_task_metadata(
                    job,
                    task_id=celery_task_id,
                    case_id=case_id,
                    filename=filename,
                )
                session.commit()

    return {
        "outcome": "enqueued",
        "http_status": 202,
        "import_job_id": import_job_id,
        "task_id": celery_task_id,
        "case_id": case_id,
    }
