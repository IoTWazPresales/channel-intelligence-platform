"""Enqueue shipment product re-resolution after catalog commits (avoids import cycles)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.background_tasks.store import BackgroundTaskStore
from app.services.imports.shipment_evidence_product_reresolution import (
    count_all_shipment_evidence_lines,
    rerun_shipment_product_resolution_all_lines,
)

logger = logging.getLogger(__name__)


def enqueue_shipment_evidence_product_reresolution(
    *,
    trigger: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Queue Celery task (or daemon thread fallback) to re-resolve products for all shipment evidence lines."""
    with SessionLocal() as db:
        lines_total = count_all_shipment_evidence_lines(db)
    if lines_total == 0:
        return {
            "outcome": "skipped",
            "message": "No shipment evidence lines found.",
            "task_id": None,
            "lines_total": 0,
        }

    store = BackgroundTaskStore()
    default_title = "Re-resolving shipment evidence products"
    task_id = store.create_task(
        task_type="shipment_product_reresolution",
        title=title or default_title,
        status="queued",
        import_job_id=None,
        related_import_job_ids=[],
        extra={"trigger": trigger},
    )

    def _run_sync(tid: str | None) -> None:
        try:
            if tid:
                store.update_task(tid, status="running")
            with SessionLocal() as db:

                def cb(meta: dict[str, Any]) -> None:
                    if tid:
                        store.update_task(
                            tid,
                            lines_total=meta.get("lines_total"),
                            lines_processed=meta.get("lines_processed"),
                            newly_resolved=meta.get("newly_resolved"),
                            still_unresolved=meta.get("still_unresolved"),
                        )

                rerun_shipment_product_resolution_all_lines(db, on_progress=cb)
            if tid:
                store.update_task(tid, status="completed")
        except Exception as exc:
            logger.exception("shipment reresolution failed")
            if tid:
                store.update_task(tid, status="failed", error_message=str(exc)[:2000])

    try:
        from app.worker.tasks import shipment_evidence_reresolution_task

        shipment_evidence_reresolution_task.delay(task_id or "", trigger)
    except Exception:
        logger.warning(
            "Celery dispatch failed for shipment reresolution; falling back to daemon thread.",
            exc_info=True,
        )
        threading.Thread(target=_run_sync, args=(task_id,), name="shipment-reresolution", daemon=True).start()

    return {
        "outcome": "enqueued",
        "message": "Shipment product re-resolution started.",
        "task_id": task_id,
        "lines_total": lines_total,
    }


def enqueue_shipment_evidence_product_reresolution_after_pm_commit() -> None:
    """Called after successful Product Master commit: re-resolve all shipment evidence lines."""
    try:
        enqueue_shipment_evidence_product_reresolution(trigger="post_pm_commit")
    except Exception:
        logger.exception("post-PM shipment reresolution enqueue failed")
