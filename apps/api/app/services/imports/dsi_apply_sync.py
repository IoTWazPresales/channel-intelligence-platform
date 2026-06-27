"""Synchronous worker for applying a ``distributor_inventory`` (DSI) import job.

Backgrounded counterpart to the old in-request DSI apply path. Runs exactly the two steps the
endpoint used to run inline — the DSI pipeline in ``apply`` mode (refresh staging resolutions to
``validated``) then ``complete_dsi_import_job_to_loaded`` (fact upsert → ``loaded``, which itself
dispatches the existing SOH / velocity / forecasting derivation tasks) — but as a Celery task (or
dev in-process thread) with progress callbacks, so the HTTP request returns immediately instead of
holding a connection open for the full apply on large weekly files.

DSI validate already runs on Celery (``imports.process_job``); this brings apply to the same bar.
Semantics are unchanged: SOH stays calculated-not-stored (derivations run as their own tasks),
``source_key`` fact upsert / latest-job-wins preserved, no schema change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_FAILED, STAGE_LOADED, STAGE_VALIDATED, process_import_job_sync
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob
from app.services.imports.dsi_apply_completion import (
    DsiApplyCompletionError,
    complete_dsi_import_job_to_loaded,
)
from app.services.imports.import_job_background_metadata import persist_clear_background_task_metadata

# (phase, phase_label, current_row, total_rows) — the shape the dsi-progress reader understands.
ProgressFn = Callable[[str, str, int, int], None]


def run_dsi_apply_sync(job_id: int, *, on_progress: ProgressFn | None = None) -> dict[str, Any]:
    """Apply a DSI job: pipeline (apply) → complete-to-loaded. Mirrors the prior inline endpoint work.

    Returns a small summary used by the synchronous fallback path; the Celery/thread path discards it.
    On a DSI business-rule failure the job is marked ``failed`` with the rule message in
    ``error_summary`` (so the progress poll surfaces it), matching the old endpoint's 422 detail.
    """

    def _emit(phase: str, label: str, current: int, total: int) -> None:
        if on_progress is not None:
            try:
                on_progress(phase, label, current, total)
            except Exception:
                pass

    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None or (job.template_slug or "") != "distributor_inventory":
            return {"id": job_id, "outcome": "not_found"}
        # Normal flow: the job was just validated and the user clicked "Continue to apply".
        # Step 2 (complete_dsi_import_job_to_loaded) re-resolves every staging line against
        # current master data and upserts facts on its own, so re-running the entire
        # parse + 178k-row resolution pipeline here is pure redundant work — it is exactly
        # the "why does apply revalidate again" problem. Only run the pipeline when the job
        # is NOT already validated with staging present (defensive fallback for an apply on
        # a job that never went through validate).
        already_validated = (job.stage or "") == STAGE_VALIDATED and bool(
            db.scalar(
                select(func.count())
                .select_from(ImportDistributorSiStagingLine)
                .where(ImportDistributorSiStagingLine.import_job_id == job_id)
            )
        )

    # Step 1 — DSI pipeline in apply mode (refresh staging → validated), with row progress.
    # Skipped on the normal validated→apply path; Step 2 does the resolution refresh + fact upsert.
    if not already_validated:
        with SessionLocal() as db:
            process_import_job_sync(db, job_id, on_progress=on_progress)

    # Step 2 — finalize: fact upsert + promote to loaded + dispatch derivation tasks.
    _emit("finalizing_apply", "Finalizing DSI apply", 0, 0)
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if (
            job is not None
            and (job.template_slug or "") == "distributor_inventory"
            and (job.stage or "") == STAGE_VALIDATED
            and (job.import_mode or "") == "apply"
        ):
            try:
                complete_dsi_import_job_to_loaded(db, job_id)
            except DsiApplyCompletionError as exc:
                fail = db.get(ImportJob, job_id)
                if fail is not None:
                    fail.status = "failed"
                    fail.stage = STAGE_FAILED
                    fail.error_summary = str(exc)[:2000]
                    fail.completed_at = datetime.now(timezone.utc)
                    persist_clear_background_task_metadata(db, fail)
                    db.commit()
                _emit("failed", "DSI apply failed", 0, 0)
                return {"id": job_id, "outcome": "completion_error", "error": str(exc)}

    # Clear the background-task slot once the job has reached a terminal stage.
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        outcome = "applied"
        if job is not None:
            if (job.stage or "") == STAGE_LOADED:
                persist_clear_background_task_metadata(db, job)
                db.commit()
            else:
                outcome = "not_completed"

    _emit("complete", "Apply complete", 0, 0)
    return {"id": job_id, "outcome": outcome}
