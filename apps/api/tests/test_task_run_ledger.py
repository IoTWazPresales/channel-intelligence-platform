"""Unit tests for task_run ledger writes (no Celery broker required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.task_run_ledger import (
    STATE_FAILED,
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_SUCCEEDED,
    TRANSPORT_BROKER,
    create_queued_task_run,
    heartbeat_task_run,
    mark_task_run_running,
    task_run_execution,
)


def _mock_session_local() -> tuple[MagicMock, MagicMock]:
    db = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = db
    session_cm.__exit__.return_value = False
    return session_cm, db


def test_create_queued_task_run_inserts_row() -> None:
    session_cm, db = _mock_session_local()
    db.get.return_value = None
    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        create_queued_task_run(
            task_run_id="task-1",
            task_name="imports.process_job",
            entity_type="import_job",
            entity_id=42,
            transport=TRANSPORT_BROKER,
        )
    db.get.assert_called_once()
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.id == "task-1"
    assert added.state == STATE_QUEUED
    assert added.entity_id == 42
    db.commit.assert_called_once()


def test_mark_task_run_running_updates_existing_row() -> None:
    session_cm, db = _mock_session_local()
    row = MagicMock()
    row.state = STATE_QUEUED
    row.started_at = None
    db.get.return_value = row
    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        mark_task_run_running("task-2")
    assert row.state == STATE_RUNNING
    assert row.started_at is not None
    db.commit.assert_called_once()


def test_task_run_execution_marks_terminal_states() -> None:
    session_cm, db = _mock_session_local()
    row = MagicMock()
    row.state = STATE_QUEUED
    row.started_at = None
    db.get.return_value = row

    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        with task_run_execution("task-3"):
            pass

    assert row.state == STATE_SUCCEEDED
    assert row.finished_at is not None

    row.state = STATE_QUEUED
    row.started_at = None
    row.finished_at = None
    try:
        with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
            with task_run_execution("task-4"):
                raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert row.state == STATE_FAILED


def test_heartbeat_task_run_sets_timestamp() -> None:
    session_cm, db = _mock_session_local()
    row = MagicMock()
    row.state = STATE_RUNNING
    row.heartbeat_at = None
    db.get.return_value = row
    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        heartbeat_task_run("task-5")
    assert row.heartbeat_at is not None
    db.commit.assert_called_once()
