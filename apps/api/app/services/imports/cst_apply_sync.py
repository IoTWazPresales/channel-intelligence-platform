"""Synchronous worker for applying a ``customer_sell_through`` import job (N-0111).

The sell-through Apply step, on the shipment / DSI apply pattern (import-parity rule 2): the
endpoint marks the job running and dispatches ``imports.cst_apply``; the worker runs this, which
marks steward-mapped rows resolved, upserts the matched rows not loaded yet (batched, with
progress) and moves the job to ``loaded``. Unmatched and ignored rows stay out and are counted in
the job's load report. Safe to re-run: rows already applied are not written again.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_LOADED
from app.models.ingestion import ImportJob
from app.services.imports.import_job_background_metadata import (
    persist_clear_background_task_metadata,
    persist_pipeline_worker_started_at,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, str, int, int], None]

CST_TEMPLATE_SLUG = "customer_sell_through"


def run_cst_apply_sync(db: Session, job_id: int, *, on_progress: ProgressFn | None = None) -> dict[str, Any]:
    from app.services.imports.cst_mapping_candidates import mark_steward_mapped_cst_lines_resolved
    from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

    def _emit(phase: str, label: str, current: int, total: int) -> None:
        if on_progress is not None:
            try:
                on_progress(phase, label, current, total)
            except Exception:
                pass

    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != CST_TEMPLATE_SLUG:
        return {"id": job_id, "outcome": "not_found"}

    persist_pipeline_worker_started_at(db, job)
    db.commit()

    _emit("marking_matched", "Marking rows matched in the steward", 0, 0)
    marked = mark_steward_mapped_cst_lines_resolved(db, job_id)

    def _facts_progress(current: int, total: int) -> None:
        _emit("writing_facts", "Writing sell-through facts", current, total)

    _emit("writing_facts", "Writing sell-through facts", 0, 0)
    try:
        summary = apply_customer_sellthrough_staging(db, job_id, on_progress=_facts_progress)
        if summary.errors:
            raise RuntimeError(" · ".join(summary.errors))
        db.commit()
    except Exception as exc:
        logger.exception("run_cst_apply_sync failed job_id=%s", job_id)
        try:
            db.rollback()
        except Exception:
            pass
        return record_cst_apply_failure(job_id, exc)

    job = db.get(ImportJob, job_id)
    if job is not None:
        job.import_mode = "apply"
        job.stage = STAGE_LOADED
        # As shipment apply: facts written → completed + loaded; rows left out are in the load report.
        job.status = "completed"
        job.error_summary = None
        job.completed_at = datetime.now(timezone.utc)
        persist_clear_background_task_metadata(db, job)
        db.commit()
    _emit("done", "Done", 1, 1)
    return {
        "id": job_id,
        "outcome": "loaded",
        "marked_resolved": marked,
        "applied": summary.applied,
        "skipped_unresolved": summary.skipped_unresolved,
    }


def record_cst_apply_failure(job_id: int, exc: BaseException) -> dict[str, Any]:
    """Write the failure back on a clean session (never re-raises); the job stays validated."""
    msg = (str(exc).strip() or exc.__class__.__name__)[:500]
    try:
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job is not None:
                job.status = "completed_with_errors"
                job.error_summary = f"Apply failed: {msg}"
                persist_clear_background_task_metadata(db, job)
                db.commit()
    except Exception:
        logger.exception("record_cst_apply_failure could not write back job_id=%s", job_id)
    return {"id": job_id, "outcome": "failed", "error": msg}
