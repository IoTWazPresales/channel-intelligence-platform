"""HTTP-facing bulk lineup backfill preview + apply (Spec C Step B)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob
from app.services.commercial_planner.lineup_bulk_backfill_apply import (
    apply_bulk_lineup_batch_sync,
    load_preview_session,
    persist_preview_session,
)
from app.services.commercial_planner.lineup_bulk_backfill_preview import (
    BulkFileInput,
    build_bulk_lineup_preview,
)
from app.services.imports.import_background_slots import SLOT_MAIN, set_task_slot_on_job
from app.services.task_run_ledger import (
    ENTITY_IMPORT_JOB,
    TRANSPORT_BROKER,
    TRANSPORT_IN_PROCESS_THREAD,
    create_queued_task_run,
    spawn_in_process_thread_with_ledger,
)

logger = logging.getLogger(__name__)


async def execute_bulk_lineup_preview(
    db: AsyncSession,
    files: list[tuple[str, bytes, str | None]],
    *,
    manual_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse files in-memory, persist preview session on ImportJob (no lineup writes)."""
    inputs = [
        BulkFileInput(filename=name, file_bytes=data, folder_path=folder)
        for name, data, folder in files
    ]
    preview = await build_bulk_lineup_preview(db, inputs, manual_overrides=manual_overrides)
    session_job = await persist_preview_session(db, preview)
    return {
        "session_import_job_id": int(session_job.id),
        "preview": preview,
    }


async def execute_bulk_lineup_apply(
    db: AsyncSession,
    session_job_id: int,
    *,
    approved_proposal_keys: list[str] | None = None,
    excluded_proposal_keys: list[str] | None = None,
    supersession_confirmations: dict[str, str] | None = None,
    commercial_plan_id: int | None = None,
) -> dict[str, Any]:
    """Validate session then dispatch batch apply async (writes cases — not a backfill soak)."""
    preview = await load_preview_session(db, session_job_id)
    _ = preview  # existence check

    settings = get_settings()
    task_name = "commercial_planner.bulk_lineup_backfill_apply"
    celery_task_id: str | None = None

    def _run_sync() -> dict[str, Any]:
        return apply_bulk_lineup_batch_sync(
            session_job_id,
            approved_proposal_keys=approved_proposal_keys,
            excluded_proposal_keys=excluded_proposal_keys,
            supersession_confirmations=supersession_confirmations,
            commercial_plan_id=commercial_plan_id,
        )

    if settings.cip_dev_celery_dispatch == "in_process_thread":
        celery_task_id = "dev-in-process-thread"
        create_queued_task_run(
            task_run_id=celery_task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=session_job_id,
            transport=TRANSPORT_IN_PROCESS_THREAD,
        )
        spawn_in_process_thread_with_ledger(
            task_run_id=celery_task_id,
            thread_name=f"bulk-lineup-apply-{session_job_id}",
            target=_run_sync,
        )
    else:
        celery_task_id = f"bulk-lineup-apply-{session_job_id}"
        create_queued_task_run(
            task_run_id=celery_task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=session_job_id,
            transport=TRANSPORT_IN_PROCESS_THREAD,
        )
        spawn_in_process_thread_with_ledger(
            task_run_id=celery_task_id,
            thread_name=f"bulk-lineup-apply-{session_job_id}",
            target=_run_sync,
        )

    job = await db.get(ImportJob, session_job_id)
    if job is not None and celery_task_id:
        set_task_slot_on_job(
            job,
            SLOT_MAIN,
            task_id=celery_task_id,
            label="Bulk lineup backfill apply…",
        )
        await db.commit()

    return {
        "async": True,
        "session_import_job_id": session_job_id,
        "task_id": celery_task_id,
    }
