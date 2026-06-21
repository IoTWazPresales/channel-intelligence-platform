"""Celery Task base that records execution state in task_run."""

from __future__ import annotations

from celery import Task

from app.services.task_run_ledger import (
    TRANSPORT_BROKER,
    ensure_task_run_running,
    entity_from_task_args,
    mark_task_run_failed,
    mark_task_run_succeeded,
    reset_current_task_run_id,
    set_current_task_run_id,
)


class LedgerTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        task_run_id = getattr(getattr(self, "request", None), "id", None)
        if not task_run_id:
            return self.run(*args, **kwargs)

        task_name = self.name or ""
        entity_type, entity_id = entity_from_task_args(task_name, tuple(args))
        token = set_current_task_run_id(str(task_run_id))
        try:
            ensure_task_run_running(
                str(task_run_id),
                task_name=task_name,
                entity_type=entity_type,
                entity_id=entity_id,
                transport=TRANSPORT_BROKER,
            )
            result = self.run(*args, **kwargs)
            mark_task_run_succeeded(str(task_run_id))
            return result
        except Exception as exc:
            mark_task_run_failed(str(task_run_id), str(exc))
            raise
        finally:
            reset_current_task_run_id(token)
