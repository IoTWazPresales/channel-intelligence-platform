"""Cancel/retry import job background tasks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.imports.import_job_task_control import (
    cancel_import_job_sync,
    prepare_import_job_retry_sync,
)


def test_cancel_import_job_revokes_clears_and_marks_failed() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 7
    mock_job.status = "running"
    mock_job.staged_metadata = {"celery_task_id": "task-abc", "dsi_bulk_task": {"task_id": "bulk-1"}}
    mock_session.get.return_value = mock_job

    with patch("app.services.imports.import_job_task_control._revoke_celery_tasks") as mock_revoke:
        out = cancel_import_job_sync(mock_session, 7)

    mock_revoke.assert_called_once_with(["task-abc", "bulk-1"])
    assert mock_job.status == "failed"
    assert mock_job.error_summary == "Cancelled by user"
    assert mock_job.staged_metadata is None
    assert out == {"cancelled": True, "job_id": 7, "previous_status": "running"}
    mock_session.commit.assert_called_once()


def test_cancel_import_job_stale_no_celery_ids() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 8
    mock_job.status = "pending"
    mock_job.staged_metadata = {"celery_task_id": "stale-id"}
    mock_session.get.return_value = mock_job

    with patch("app.services.imports.import_job_task_control._revoke_celery_tasks") as mock_revoke:
        out = cancel_import_job_sync(mock_session, 8)

    mock_revoke.assert_called_once_with(["stale-id"])
    assert out["cancelled"] is True
    assert mock_job.status == "failed"


def test_prepare_import_job_retry_requires_failed() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.status = "running"
    mock_job.template_slug = "distributor_inventory"
    mock_session.get.return_value = mock_job

    try:
        prepare_import_job_retry_sync(mock_session, 1)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "job_not_failed"


def test_prepare_import_job_retry_resets_job() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 9
    mock_job.status = "failed"
    mock_job.error_summary = "Cancelled by user"
    mock_job.template_slug = "distributor_inventory"
    mock_job.staged_metadata = None
    mock_session.get.return_value = mock_job

    job = prepare_import_job_retry_sync(mock_session, 9)

    assert job.status == "pending"
    assert job.error_summary is None
    assert job.stage == "dsi_mapping_ready"
    mock_session.commit.assert_called_once()
