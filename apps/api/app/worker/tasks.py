import logging

from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.ingestion.pipeline import process_import_job_sync
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


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


@celery_app.task(name="imports.process_job")
def process_import_job_task(job_id: int) -> int:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        process_import_job_sync(db, job_id)
    return job_id


@celery_app.task(name="imports.product_master_commit", bind=True, ack_late=True)
def product_master_commit_task(self, job_id: int, confirm_destructive: bool) -> int:
    """Background Product Master apply: must be enqueued via try_enqueue_pm_commit_sync first."""
    celery_id = getattr(getattr(self, "request", None), "id", None)
    return run_product_master_commit_job(
        job_id,
        confirm_destructive,
        celery_task_id=str(celery_id) if celery_id else None,
    )


@celery_app.task(name="imports.shipment_evidence_product_reresolution", bind=True, ack_late=True)
def shipment_evidence_reresolution_task(self, task_id: str, trigger: str) -> str:
    """Re-run product resolution for all shipment evidence lines (catalog refresh)."""
    from app.db.session_sync import SessionLocal
    from app.services.background_tasks.store import BackgroundTaskStore
    from app.services.imports.shipment_evidence_product_reresolution import (
        rerun_shipment_product_resolution_all_lines,
    )

    store = BackgroundTaskStore()
    if task_id:
        store.update_task(task_id, status="running", trigger=trigger)

    try:
        with SessionLocal() as db:

            def _cb(meta: dict) -> None:
                if task_id:
                    store.update_task(
                        task_id,
                        lines_total=meta.get("lines_total"),
                        lines_processed=meta.get("lines_processed"),
                        newly_resolved=meta.get("newly_resolved"),
                        still_unresolved=meta.get("still_unresolved"),
                    )

            rerun_shipment_product_resolution_all_lines(db, on_progress=_cb)
        if task_id:
            store.update_task(task_id, status="completed")
    except Exception:
        logger.exception("shipment_evidence_reresolution_task failed trigger=%s", trigger)
        if task_id:
            store.update_task(task_id, status="failed", error_message="Re-resolution failed; see server logs.")
        raise
    return task_id or "ok"
