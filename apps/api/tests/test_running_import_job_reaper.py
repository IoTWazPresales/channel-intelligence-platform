"""Tests for periodic running import job reaper (Celery beat)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.services.imports.running_import_job_reaper import (
    _is_reap_candidate,
    reap_stale_running_import_jobs_sync,
)


def _meta(*, queued_minutes_ago: int = 10, checkpoint_minutes_ago: int | None = 6) -> dict:
    now = datetime.now(timezone.utc)
    meta = {"pipeline_queued_at": (now - timedelta(minutes=queued_minutes_ago)).isoformat()}
    if checkpoint_minutes_ago is not None:
        meta["dsi_validate_checkpoint_at"] = (now - timedelta(minutes=checkpoint_minutes_ago)).isoformat()
    return meta


def test_is_reap_candidate_skips_when_task_still_active() -> None:
    ok, _ = _is_reap_candidate(
        task_id="task-1",
        active_ids={"task-1"},
        meta=_meta(),
        now=datetime.now(timezone.utc),
    )
    assert ok is False


def test_is_reap_candidate_skips_during_dispatch_grace() -> None:
    ok, _ = _is_reap_candidate(
        task_id="task-1",
        active_ids=set(),
        meta=_meta(queued_minutes_ago=1),
        now=datetime.now(timezone.utc),
    )
    assert ok is False


def test_is_reap_candidate_marks_when_not_active_and_checkpoint_stale() -> None:
    ok, reason = _is_reap_candidate(
        task_id="task-1",
        active_ids=set(),
        meta=_meta(checkpoint_minutes_ago=10),
        now=datetime.now(timezone.utc),
    )
    assert ok is True
    assert "stale" in reason.lower()


def test_is_reap_candidate_marks_when_not_active_even_if_checkpoint_fresh() -> None:
    ok, reason = _is_reap_candidate(
        task_id="task-1",
        active_ids=set(),
        meta=_meta(checkpoint_minutes_ago=1),
        now=datetime.now(timezone.utc),
    )
    assert ok is True
    assert "inspect/active" in reason


def test_reap_skips_when_inspect_unavailable() -> None:
    with patch(
        "app.services.imports.running_import_job_reaper.collect_active_celery_task_ids",
        return_value=None,
    ):
        out = reap_stale_running_import_jobs_sync()
    assert out["inspected"] is False
    assert out["marked_failed"] == 0


def test_reap_marks_running_job_when_task_not_active() -> None:
    mock_job = MagicMock()
    mock_job.id = 43
    mock_job.staged_metadata = {
        "celery_task_id": "dead-task",
        **_meta(checkpoint_minutes_ago=10),
    }

    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch(
            "app.services.imports.running_import_job_reaper.collect_active_celery_task_ids",
            return_value=set(),
        ),
        patch(
            "app.services.imports.running_import_job_reaper.SessionLocal",
        ) as mock_session_local,
    ):
        mock_session_local.return_value.__enter__.return_value = mock_session
        out = reap_stale_running_import_jobs_sync()

    assert out["marked_failed"] == 1
    assert out["job_ids"] == [43]
    assert mock_job.status == "failed"
    assert mock_job.error_summary
    mock_session.commit.assert_called_once()


def test_reap_skips_dev_in_process_thread() -> None:
    mock_job = MagicMock()
    mock_job.id = 99
    mock_job.staged_metadata = {"celery_task_id": "dev-in-process-thread", **_meta()}

    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch(
            "app.services.imports.running_import_job_reaper.collect_active_celery_task_ids",
            return_value=set(),
        ),
        patch(
            "app.services.imports.running_import_job_reaper.SessionLocal",
        ) as mock_session_local,
    ):
        mock_session_local.return_value.__enter__.return_value = mock_session
        out = reap_stale_running_import_jobs_sync()

    assert out["marked_failed"] == 0
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()
