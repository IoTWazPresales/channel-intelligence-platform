"""Async dispatch for full distributor merge (task_run ledger + dev poll cache)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.distributor_full_merge import DistributorFullMergeError, confirm_distributor_full_merge_sync

logger = logging.getLogger(__name__)

TASK_NAME = "distributors.full_merge_confirm"

_dev_merge_task_results: dict[str, dict[str, Any]] = {}


def dev_distributor_full_merge_results() -> dict[str, dict[str, Any]]:
    return _dev_merge_task_results


def enqueue_distributor_full_merge_confirm(payload: dict[str, Any]) -> tuple[str, bool]:
    from app.core.config import get_settings
    from app.core.dev_celery_logging import DEV_CELERY_LOGGER
    from app.services.task_run_ledger import (
        ENTITY_DISTRIBUTOR_FULL_MERGE,
        TRANSPORT_BROKER,
        TRANSPORT_IN_PROCESS_THREAD,
        TRANSPORT_INLINE_SYNC,
        create_queued_task_run,
        run_inline_with_ledger,
        spawn_in_process_thread_with_ledger,
    )
    from app.worker.celery_app import celery_app

    settings = get_settings()

    def _sync_work() -> dict[str, Any]:
        with SessionLocal() as db:
            return confirm_distributor_full_merge_sync(
                db,
                similarity_key=str(payload["similarity_key"]),
                survivor_id=int(payload["survivor_id"]),
                audit_note=str(payload["audit_note"]),
                performed_by=payload.get("performed_by"),
                distributor_ids=payload.get("distributor_ids"),
            )

    try:
        result = celery_app.send_task(TASK_NAME, args=[payload], ignore_result=True)
        task_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_id,
            task_name=TASK_NAME,
            entity_type=ENTITY_DISTRIBUTOR_FULL_MERGE,
            entity_id=int(payload.get("survivor_id") or 0),
            transport=TRANSPORT_BROKER,
        )
        return task_id, True
    except Exception:
        logger.exception("distributor full merge Celery enqueue failed")
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"thread-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_id,
                task_name=TASK_NAME,
                entity_type=ENTITY_DISTRIBUTOR_FULL_MERGE,
                entity_id=int(payload.get("survivor_id") or 0),
                transport=TRANSPORT_IN_PROCESS_THREAD,
            )

            def _thread_target() -> None:
                try:
                    out = _sync_work()
                    _dev_merge_task_results[task_id] = {"state": "SUCCESS", "result": out}
                except Exception as exc:
                    _dev_merge_task_results[task_id] = {
                        "state": "FAILURE",
                        "error": str(exc)[:800],
                    }
                    raise

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: distributor full merge — in-process thread after broker failure (DEV ONLY)."
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_id,
                thread_name="distributor-full-merge",
                target=_thread_target,
            )
            return task_id, True

        task_id = f"inline-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=TASK_NAME,
            entity_type=ENTITY_DISTRIBUTOR_FULL_MERGE,
            entity_id=int(payload.get("survivor_id") or 0),
            transport=TRANSPORT_INLINE_SYNC,
        )

        def _inline() -> dict[str, Any]:
            try:
                return _sync_work()
            except DistributorFullMergeError as exc:
                raise ValueError(str(exc)) from exc

        out = run_inline_with_ledger(task_id, _inline)
        _dev_merge_task_results[task_id] = {"state": "SUCCESS", "result": out}
        return task_id, False
