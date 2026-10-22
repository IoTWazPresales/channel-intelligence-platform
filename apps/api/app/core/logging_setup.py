"""Give the API's own loggers a timestamp and level (N-0089 log view).

Before this the API had no logging configuration: ``app.*`` messages went through Python's last-resort handler,
so only WARNING and above appeared in ``api.err.log``, bare, with no time or level. The ``app`` logger now writes
INFO and above to stderr in the same shape Celery uses in ``worker.err.log``::

    [2026-10-22 21:51:22,858: INFO/app.services.imports.cst_apply_sync] message

uvicorn's own loggers are untouched. Not applied under pytest, so test output and ``caplog`` stay as they were.
"""

from __future__ import annotations

import logging
import sys

from app.core.job_log_context import install_job_log_tagging

APP_LOG_FORMAT = "[%(asctime)s: %(levelname)s/%(name)s] %(message)s"
_HANDLER_FLAG = "_cip_app_log_handler"


def configure_api_app_logging(*, force: bool = False) -> bool:
    """Attach the stderr handler to the ``app`` logger once. Returns True when it did."""
    install_job_log_tagging()
    if "pytest" in sys.modules and not force:
        return False
    app_logger = logging.getLogger("app")
    if any(getattr(h, _HANDLER_FLAG, False) for h in app_logger.handlers):
        return False
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(APP_LOG_FORMAT))
    setattr(handler, _HANDLER_FLAG, True)
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    return True
