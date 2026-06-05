"""Shared async-dispatch helper for import worker tasks (BACKLOG-022).

Extracted from ``app.api.v1.endpoints.imports._enqueue_import_worker_task`` to avoid
duplicating the same broker/fallback logic in every new import endpoint that needs
async dispatch (CST apply is the third caller that triggers extraction per BACKLOG-022).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def enqueue_import_worker_task(
    job_id: int,
    *,
    task_name: str,
    log_label: str,
    in_process_thread_name: str,
    sync_work: Callable[[Session, int], Any],
) -> tuple[bool, str | None]:
    """Publish ``task_name`` to the Celery broker; mirror upload/validate fallback semantics.

    Uses ``celery_app.send_task`` so dispatch matches the worker-registered task name regardless
    of import binding order. On broker failure: dev-only in-process thread when
    ``CIP_DEV_CELERY_DISPATCH=in_process_thread``, otherwise run ``sync_work`` inline in this process.

    Returns ``(dispatched, task_id)`` where dispatched is ``True`` when the HTTP layer should treat
    the operation as async (broker accepted the message, or a dev thread was started), and
    ``task_id`` is the Celery task ID when dispatched via the broker (``None`` otherwise).
    """
    from app.core.config import get_settings
    from app.core.dev_celery_logging import DEV_CELERY_LOGGER
    from app.db.session_sync import SessionLocal
    from app.worker.celery_app import celery_app

    settings = get_settings()
    try:
        result = celery_app.send_task(task_name, args=[job_id], ignore_result=True)
        return True, result.id
    except Exception:
        logger.exception("%s: Celery enqueue failed job_id=%s task=%s", log_label, job_id, task_name)
        if settings.cip_dev_celery_dispatch == "in_process_thread":

            def _in_process() -> None:
                try:
                    with SessionLocal() as s2:
                        sync_work(s2, job_id)
                except Exception:
                    logger.exception(
                        "%s: in-process thread failed job_id=%s "
                        "(CIP_DEV_CELERY_DISPATCH=in_process_thread after broker failure)",
                        log_label,
                        job_id,
                    )

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: %s job_id=%s — in-process thread after broker failure (DEV ONLY).",
                log_label,
                job_id,
            )
            threading.Thread(target=_in_process, name=in_process_thread_name, daemon=True).start()
            return True, None
        with SessionLocal() as sync_fallback:
            sync_work(sync_fallback, job_id)
        return False, None
