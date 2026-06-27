"""Async dispatch for customer alias-scope merge (task_run ledger + dev poll cache)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.customer_alias_scope_merge import (
    CustomerAliasScopeMergeError,
    confirm_customer_alias_scope_merge_sync,
)

logger = logging.getLogger(__name__)

TASK_NAME = "customers.alias_scope_merge_confirm"

_dev_merge_task_results: dict[str, dict[str, Any]] = {}


def dev_customer_alias_scope_merge_results() -> dict[str, dict[str, Any]]:
    return _dev_merge_task_results


def enqueue_customer_alias_scope_merge_confirm(payload: dict[str, Any]) -> tuple[str, bool]:
    """Return ``(task_id, async_poll)``."""
    from app.core.config import get_settings
    from app.core.dev_celery_logging import DEV_CELERY_LOGGER
    from app.services.task_run_ledger import (
        ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE,
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
            return confirm_customer_alias_scope_merge_sync(
                db,
                normalized_token=str(payload["normalized_token"]),
                source_definition_id=payload.get("source_definition_id"),
                distributor_id=payload.get("distributor_id"),
                survivor_id=int(payload["survivor_id"]),
                audit_note=str(payload["audit_note"]),
                performed_by=payload.get("performed_by"),
            )

    try:
        result = celery_app.send_task(TASK_NAME, args=[payload], ignore_result=True)
        task_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_id,
            task_name=TASK_NAME,
            entity_type=ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE,
            entity_id=int(payload.get("survivor_id") or 0),
            transport=TRANSPORT_BROKER,
        )
        return task_id, True
    except Exception:
        logger.exception("customer alias-scope merge Celery enqueue failed")
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_id = f"thread-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_id,
                task_name=TASK_NAME,
                entity_type=ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE,
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
                "ENQUEUE: customer alias-scope merge — in-process thread after broker failure (DEV ONLY)."
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_id,
                thread_name="customer-alias-scope-merge",
                target=_thread_target,
            )
            return task_id, True

        task_id = f"inline-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_id,
            task_name=TASK_NAME,
            entity_type=ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE,
            entity_id=int(payload.get("survivor_id") or 0),
            transport=TRANSPORT_INLINE_SYNC,
        )

        def _inline() -> dict[str, Any]:
            try:
                return _sync_work()
            except CustomerAliasScopeMergeError as exc:
                raise ValueError(str(exc)) from exc

        out = run_inline_with_ledger(task_id, _inline)
        _dev_merge_task_results[task_id] = {"state": "SUCCESS", "result": out}
        return task_id, False
