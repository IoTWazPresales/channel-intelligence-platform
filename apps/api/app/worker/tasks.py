import logging

from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.ingestion.pipeline import process_import_job_sync
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _write_task_level_failure(job_id: int) -> None:
    """Best-effort STAGE_FAILED writeback for exceptions that escape process_import_job_sync.

    Called when an exception is raised outside the inner try/except in the pipeline (e.g.
    RawFileMetadata not found, storage read failure, or post-processing hook failure). The inner
    handler already covers exceptions inside the pipeline try block, so this is a safety net for
    the edges that sit outside it.
    """
    from datetime import datetime, timezone

    from app.db.session_sync import SessionLocal
    from app.ingestion.pipeline import STAGE_FAILED
    from app.models.ingestion import ImportJob

    try:
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job and job.stage != STAGE_FAILED:
                job.status = "failed"
                job.stage = STAGE_FAILED
                job.error_summary = "Task-level failure; see worker log for exception detail."
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
    except Exception:
        logger.exception("STAGE_FAILED writeback also failed job_id=%s", job_id)


def run_product_master_commit_job(
    job_id: int,
    confirm_destructive: bool,
    *,
    celery_task_id: str | None,
) -> int:
    """Shared implementation for Celery worker and explicit dev-only dispatch paths."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.product_master_workflow import run_pm_commit_worker

    if celery_task_id == "dev-in-process-thread":
        DEV_CELERY_LOGGER.warning(
            "EXECUTION: Product Master commit job_id=%s running in-process (DEV ONLY, "
            "CIP_DEV_CELERY_DISPATCH=in_process_thread). Not broker-isolated.",
            job_id,
        )

    try:
        with SessionLocal() as db:
            run_pm_commit_worker(
                db,
                job_id,
                confirm_destructive=confirm_destructive,
                celery_task_id=celery_task_id,
            )
    except Exception:
        logger.exception("product_master_commit job failed job_id=%s", job_id)
        raise
    return job_id


@celery_app.task(name="imports.process_job", bind=True)
def process_import_job_task(self, job_id: int) -> int:
    from app.db.session_sync import SessionLocal

    def _on_progress(phase: str, phase_label: str, current_row: int, total_rows: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "phase_label": phase_label,
                    "current_row": current_row,
                    "total_rows": total_rows,
                    "pct": round(current_row / total_rows * 100) if total_rows else 0,
                },
            )
        except Exception:
            pass

    try:
        with SessionLocal() as db:
            process_import_job_sync(db, job_id, on_progress=_on_progress)
    except Exception:
        logger.exception("process_import_job_task failed job_id=%s — writing STAGE_FAILED", job_id)
        _write_task_level_failure(job_id)
        raise
    return job_id


@celery_app.task(name="imports.infer_dsi")
def infer_dsi_import_job_task(job_id: int) -> int:
    """DSI upload infer (headers + initial field_mapping → ``dsi_mapping_ready``)."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.dsi_mapping_workflow import infer_dsi_job_sync

    with SessionLocal() as db:
        infer_dsi_job_sync(db, job_id)
    return job_id


@celery_app.task(name="imports.dsi_bulk_provisional_customers", bind=True, ack_late=True)
def dsi_bulk_provisional_customers_task(self, job_id: int, payload: dict) -> dict:
    """Batch provisional customer creates for DSI bulk steward (single commit, one replan on client)."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.dsi_bulk_provisional_customers_sync import run_dsi_bulk_provisional_customers_sync

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "creating_provisional_customers",
                    "phase_label": "Creating provisional customers",
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        with SessionLocal() as db:
            return run_dsi_bulk_provisional_customers_sync(
                db, job_id, payload, on_progress=_on_progress
            )
    except Exception:
        logger.exception("dsi_bulk_provisional_customers failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_resolution_plan_apply", bind=True, ack_late=True)
def dsi_resolution_plan_apply_task(self, job_id: int, payload: dict) -> dict:
    """Apply DSI resolution-plan rows (steward map/provisional/product) with progress updates."""
    from app.services.imports.dsi_resolution_plan_apply_sync import run_dsi_resolution_plan_apply_sync

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "applying_resolution_plan",
                    "phase_label": "Applying resolution plan",
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        return run_dsi_resolution_plan_apply_sync(job_id, payload, on_progress=_on_progress)
    except Exception:
        logger.exception("dsi_resolution_plan_apply failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_soh_reconciliation", bind=True, ack_late=True)
def dsi_soh_reconciliation_task(self, job_id: int, payload: dict) -> dict:
    """Background SOH reconciliation after DSI apply."""
    from app.services.imports.dsi_soh_reconciliation_sync import run_dsi_soh_reconciliation_sync

    try:
        return run_dsi_soh_reconciliation_sync(job_id, payload)
    except Exception:
        logger.exception("dsi_soh_reconciliation failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.product_master_commit", bind=True, ack_late=True)
def product_master_commit_task(self, job_id: int, confirm_destructive: bool) -> int:
    """Background Product Master apply: must be enqueued via try_enqueue_pm_commit_sync first."""
    celery_id = getattr(getattr(self, "request", None), "id", None)
    return run_product_master_commit_job(
        job_id,
        confirm_destructive,
        celery_task_id=str(celery_id) if celery_id else None,
    )
