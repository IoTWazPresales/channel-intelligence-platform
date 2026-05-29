"""Celery/sync runner for Product Master validation."""

from __future__ import annotations

import logging

from app.db.session_sync import SessionLocal
from app.services.imports.product_master_workflow import run_pm_validate_worker

logger = logging.getLogger(__name__)


def run_product_master_validate_sync(job_id: int, *, celery_task_id: str | None = None) -> int:
    with SessionLocal() as db:
        try:
            run_pm_validate_worker(db, job_id, celery_task_id=celery_task_id)
        except Exception:
            db.rollback()
            logger.exception("run_product_master_validate_sync failed job_id=%s", job_id)
            raise
    return job_id
