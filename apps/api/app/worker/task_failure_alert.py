"""Local alert channel for Celery task failures.

The channel is a log line plus an optional file. It never opens a database
session and never writes to cip.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def emit_task_failure_alert(*, task_name: str, task_run_id: str, error: str) -> None:
    """Record a task failure on the configured channel.

    ``CIP_TASK_FAILURE_ALERT_PATH`` selects the file. When it is unset, the
    error log line is the channel.
    """
    message = f"task_failure task={task_name} run={task_run_id} error={error}"
    logger.error(message)
    raw_path = (os.environ.get("CIP_TASK_FAILURE_ALERT_PATH") or "").strip()
    if not raw_path:
        return
    target = Path(raw_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")
