"""Forced local failure must alert without opening a database session."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from celery.app.task import Context
from celery.utils.threads import LocalStack

from app.worker.ledger_task import LedgerTask
from app.worker.task_failure_alert import emit_task_failure_alert


def test_emit_task_failure_alert_appends_configured_file(tmp_path, caplog) -> None:
    target = tmp_path / "alerts.log"
    with patch.dict("os.environ", {"CIP_TASK_FAILURE_ALERT_PATH": str(target)}, clear=False):
        with caplog.at_level(logging.ERROR):
            emit_task_failure_alert(
                task_name="test.forced",
                task_run_id="run-1",
                error="forced local failure",
            )
    text = target.read_text(encoding="utf-8")
    assert "task_failure task=test.forced run=run-1 error=forced local failure" in text
    assert "forced local failure" in caplog.text


def test_ledger_task_failure_alerts_without_ledger_write(tmp_path) -> None:
    class _Boom(LedgerTask):
        name = "test.forced_failure"

        def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("forced local failure")

    task = _Boom()
    task.request_stack = LocalStack()
    task.request_stack.push(Context(id="forced-1"))
    target = tmp_path / "alerts.log"
    env = {"CIP_TASK_FAILURE_ALERT_PATH": str(target)}
    try:
        with patch.dict("os.environ", env, clear=False):
            with (
                patch("app.worker.ledger_task.ensure_task_run_running") as running,
                patch("app.worker.ledger_task.mark_task_run_failed") as failed,
                patch("app.worker.ledger_task.mark_task_run_succeeded") as succeeded,
            ):
                with pytest.raises(RuntimeError, match="forced local failure"):
                    task()
    finally:
        task.request_stack.pop()
    running.assert_called_once()
    failed.assert_called_once_with("forced-1", "forced local failure")
    succeeded.assert_not_called()
    assert "error=forced local failure" in target.read_text(encoding="utf-8")
