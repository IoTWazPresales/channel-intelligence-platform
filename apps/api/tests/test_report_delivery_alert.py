"""Import completion recomputes before notify, and delivery failure alerts without a database."""

from __future__ import annotations

import logging
from unittest.mock import patch

from app.services.report_delivery import import_event_skips_cache
from app.services.report_schedule_runner import (
    alert_report_delivery_failure,
    run_due_schedules_safe,
)


def test_import_event_recomputes_before_notify() -> None:
    assert import_event_skips_cache("import_event") is True
    assert import_event_skips_cache("schedule") is False
    assert import_event_skips_cache("manual") is False


def test_delivery_failure_alerts_without_a_database(tmp_path, caplog) -> None:
    target = tmp_path / "alerts.log"
    with patch.dict("os.environ", {"CIP_TASK_FAILURE_ALERT_PATH": str(target)}, clear=False):
        with caplog.at_level(logging.ERROR):
            alert_report_delivery_failure(
                task_name="reports.schedule_delivery",
                task_run_id="42",
                error="forced local failure",
            )
    text = target.read_text(encoding="utf-8")
    assert "task_failure task=reports.schedule_delivery run=42 error=forced local failure" in text
    assert "forced local failure" in caplog.text


def test_schedule_poll_failure_alerts(tmp_path) -> None:
    target = tmp_path / "alerts.log"
    env = {"CIP_TASK_FAILURE_ALERT_PATH": str(target)}
    with patch.dict("os.environ", env, clear=False):
        with patch(
            "app.services.report_schedule_runner.run_due_schedules_sync",
            side_effect=RuntimeError("forced local failure"),
        ):
            out = run_due_schedules_safe(reason="test")
    assert out == {"ok": False, "reason": "test"}
    assert "error=forced local failure" in target.read_text(encoding="utf-8")
