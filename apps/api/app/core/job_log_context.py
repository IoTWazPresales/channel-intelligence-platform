"""Put the import job id on every log line written while a job is being worked on (N-0089 log view).

``job_log_scope(job_id)`` sets the id for the current context; a log-record factory (installed once per
process) prefixes each line logged inside the scope with ``[job_id=N]``. The Celery ``imports.*`` tasks open
the scope from the ``task_prerun`` / ``task_postrun`` signals (``app.worker.job_log_signals``), so code that
already logs without naming the job — the validate and apply paths — is tagged without being edited.
A message that already names ``job_id=`` is left as it is.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Iterator

_current_job_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("cip_log_job_id", default=None)
_installed = False


def current_log_job_id() -> int | None:
    return _current_job_id.get()


def set_log_job_id(job_id: int | None) -> contextvars.Token:
    return _current_job_id.set(job_id)


def reset_log_job_id(token: contextvars.Token) -> None:
    _current_job_id.reset(token)


@contextmanager
def job_log_scope(job_id: int | None) -> Iterator[None]:
    token = _current_job_id.set(job_id)
    try:
        yield
    finally:
        _current_job_id.reset(token)


def install_job_log_tagging() -> None:
    """Install the record factory once; later calls do nothing."""
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = previous(*args, **kwargs)
        job_id = _current_job_id.get()
        if job_id is not None and isinstance(record.msg, str) and "job_id=" not in record.msg:
            record.msg = f"[job_id={job_id}] {record.msg}"
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
