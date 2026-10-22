"""Tag worker log lines with the import job a Celery task is working on (N-0089).

Every ``imports.*`` task takes the job id as its first argument (or ``job_id=``). On ``task_prerun`` the id goes
into the log context and one start line is written; on ``task_postrun`` one finish line (state, seconds) is
written and the context is cleared. Celery's own ``received`` / ``succeeded`` lines carry only a task uuid, so
these two lines are what ties a task to a job in the log.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from celery.signals import task_postrun, task_prerun

from app.core.job_log_context import install_job_log_tagging, reset_log_job_id, set_log_job_id

logger = logging.getLogger("app.worker.import_jobs")

install_job_log_tagging()

# task_id -> (context token, started at). One worker process runs a task at a time per thread.
_open: dict[str, tuple[Any, float]] = {}


def import_job_id_from_task(task_name: str | None, args: Any, kwargs: Any) -> int | None:
    """The job id an ``imports.*`` task works on, or None (maintenance tasks, payload-only tasks)."""
    if not (task_name or "").startswith("imports."):
        return None
    candidate = (kwargs or {}).get("job_id")
    if candidate is None and args:
        candidate = args[0]
    if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate <= 0:
        return None
    return candidate


@task_prerun.connect
def _job_log_start(task_id=None, task=None, args=None, kwargs=None, **_extra) -> None:
    job_id = import_job_id_from_task(getattr(task, "name", None), args, kwargs)
    if job_id is None or task_id is None:
        return
    _open[task_id] = (set_log_job_id(job_id), time.monotonic())
    logger.info("%s started (task %s)", task.name, task_id)


@task_postrun.connect
def _job_log_finish(task_id=None, task=None, state=None, **_extra) -> None:
    opened = _open.pop(task_id, None) if task_id is not None else None
    if opened is None:
        return
    token, started = opened
    logger.info("%s finished state=%s in %.1fs", getattr(task, "name", "?"), state, time.monotonic() - started)
    reset_log_job_id(token)
