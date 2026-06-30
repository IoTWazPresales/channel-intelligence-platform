"""Unit tests for task_run ledger writes (no Celery broker required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.task_run_ledger import (
    ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE,
    ENTITY_IMPORT_JOB,
    POLL_STATE_FAILURE,
    POLL_STATE_PENDING,
    POLL_STATE_STARTED,
    POLL_STATE_SUCCESS,
    STATE_FAILED,
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_SUCCEEDED,
    TRANSPORT_BROKER,
    create_queued_task_run,
    entity_from_task_args,
    heartbeat_task_run,
    mark_task_run_running,
    read_task_run_poll_progress_sync,
    task_run_execution,
    task_run_poll_state,
)


def _mock_session_local() -> tuple[MagicMock, MagicMock]:
    db = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = db
    session_cm.__exit__.return_value = False
    return session_cm, db


def test_entity_from_task_args_alias_scope_merge_payload_dict() -> None:
    payload = {
        "normalized_token": "vexall pty ltd",
        "source_definition_id": 12,
        "survivor_id": 296,
        "audit_note": "merge variants",
    }
    assert entity_from_task_args("customers.alias_scope_merge_confirm", (payload,)) == (
        ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE,
        296,
    )
    assert entity_from_task_args("imports.dsi_apply", (96,)) == (ENTITY_IMPORT_JOB, 96)


def test_task_run_poll_state_maps_ledger_to_celery_states() -> None:
    assert task_run_poll_state(STATE_QUEUED) == POLL_STATE_PENDING
    assert task_run_poll_state(STATE_RUNNING) == POLL_STATE_STARTED
    assert task_run_poll_state(STATE_SUCCEEDED) == POLL_STATE_SUCCESS
    assert task_run_poll_state(STATE_FAILED) == POLL_STATE_FAILURE


def test_read_task_run_poll_progress_sync() -> None:
    session_cm, db = _mock_session_local()
    row = MagicMock()
    row.state = STATE_SUCCEEDED
    row.error_summary = None
    db.get.return_value = row
    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        progress = read_task_run_poll_progress_sync("task-merge-1")
    assert progress == {"task_id": "task-merge-1", "state": POLL_STATE_SUCCESS}


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


def test_ensure_task_run_running_promotes_when_row_already_queued() -> None:
    from app.services.task_run_ledger import ensure_task_run_running

    session_cm, db = _mock_session_local()
    row = MagicMock()
    row.state = STATE_QUEUED
    row.started_at = None
    db.get.return_value = row
    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        ensure_task_run_running(
            "task-race",
            task_name="customers.full_merge_confirm",
            entity_type="customer_full_merge",
            entity_id=42,
            transport=TRANSPORT_BROKER,
        )
    assert row.state == STATE_RUNNING
    assert row.started_at is not None
    db.commit.assert_called_once()


def test_ensure_task_run_running_recovers_from_insert_race() -> None:
    from sqlalchemy.exc import IntegrityError

    from app.services.task_run_ledger import ensure_task_run_running

    session_cm, db = _mock_session_local()
    existing = MagicMock()
    existing.state = STATE_QUEUED
    existing.started_at = None
    db.get.side_effect = [None, existing]
    db.begin_nested.return_value.__enter__.return_value = None
    db.begin_nested.return_value.__exit__.return_value = False
    db.flush.side_effect = IntegrityError("insert", {}, Exception("dup"))

    with patch("app.db.session_sync.SessionLocal", return_value=session_cm):
        ensure_task_run_running(
            "task-race-2",
            task_name="customers.full_merge_confirm",
            entity_type="customer_full_merge",
            entity_id=99,
            transport=TRANSPORT_BROKER,
        )

    assert existing.state == STATE_RUNNING
    assert existing.started_at is not None
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
