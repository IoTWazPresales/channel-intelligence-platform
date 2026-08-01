"""Enqueue CST bulk ignore (S8) — broker → in-process thread → inline sync."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session import SessionLocal
from app.services.imports.cst_steward_bulk import apply_cst_steward_bulk
from app.services.task_run_ledger import (
    ENTITY_IMPORT_JOB,
    TRANSPORT_BROKER,
    TRANSPORT_INLINE_SYNC,
    TRANSPORT_IN_PROCESS_THREAD,
    create_queued_task_run,
    run_inline_with_ledger,
    spawn_in_process_thread_with_ledger,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

TASK_CST_BULK_IGNORE = "imports.cst_bulk_ignore"

_dev_cst_bulk_task_results: dict[str, dict[str, Any]] = {}


def dev_cst_bulk_task_results() -> dict[str, dict[str, Any]]:
    return _dev_cst_bulk_task_results


def run_cst_bulk_ignore_sync(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    candidate_ids = [int(x) for x in (payload.get("candidate_ids") or [])]
    with SessionLocal() as db:
        try:
            out = apply_cst_steward_bulk(
                db, job_id, action="ignore", candidate_ids=candidate_ids, product_id=None
            )
            db.commit()
            return out
        except Exception:
            db.rollback()
            raise


def enqueue_cst_bulk_task(
    *,
    task_name: str,
    job_id: int,
    payload: dict[str, Any],
    run_sync: Callable[[], dict[str, Any]],
    dev_prefix: str,
) -> tuple[str, bool]:
    settings = get_settings()
    try:
        result = celery_app.send_task(task_name, args=[job_id, payload])
        task_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        return task_id, True
    except Exception:
        logger.exception("cst_bulk: Celery enqueue failed job_id=%s task=%s", job_id, task_name)
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"dev-{dev_prefix}-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_id,
                task_name=task_name,
                entity_type=ENTITY_IMPORT_JOB,
                entity_id=job_id,
                transport=TRANSPORT_IN_PROCESS_THREAD,
            )

            def _in_process() -> None:
                try:
                    out = run_sync()
                    _dev_cst_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
                except Exception as exc:  # noqa: BLE001
                    logger.exception("cst_bulk in-process thread failed job_id=%s task_id=%s", job_id, task_id)
                    _dev_cst_bulk_task_results[task_id] = {
                        "state": "FAILURE",
                        "error": str(exc)[:800],
                    }
                    raise

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: cst_bulk %s job_id=%s — in-process thread (DEV ONLY).",
                task_name,
                job_id,
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_id,
                thread_name=f"{dev_prefix}-{job_id}",
                target=_in_process,
            )
            return task_id, True

        task_id = f"sync-{dev_prefix}-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_INLINE_SYNC,
        )

        def _inline() -> dict[str, Any]:
            out = run_sync()
            _dev_cst_bulk_task_results[task_id] = {"state": "SUCCESS", "result": out}
            return out

        run_inline_with_ledger(task_id, _inline)
        return task_id, False
