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


def test_cancel_import_job_clears_all_registered_slots() -> None:
    """Regression: cancel must clear every background-task slot, not just main/dsi_bulk.

    Previously pm_commit_task / pm_validate_task / dsi_soh/velocity/forecasting and
    lineup_parse slots survived cancel/retry and kept showing in the activity feed.
    """
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 21
    mock_job.status = "running"
    mock_job.staged_metadata = {
        "celery_task_id": "main-1",
        "pm_commit_task": {"task_id": "commit-1"},
        "dsi_soh_reconcile_task": {"task_id": "soh-1"},
        "dsi_velocity_compute_task": {"task_id": "vel-1"},
        "dsi_forecasting_task": {"task_id": "fc-1"},
        "lineup_parse_task": {"task_id": "lp-1"},
        "dsi_validate_total_rows": 5,
    }
    mock_session.get.return_value = mock_job

    with patch("app.services.imports.import_job_task_control._revoke_celery_tasks") as mock_revoke:
        cancel_import_job_sync(mock_session, 21)

    # Every slot's Celery task is revoked (registry order), not just main/dsi_bulk.
    mock_revoke.assert_called_once_with(["main-1", "soh-1", "vel-1", "fc-1", "commit-1", "lp-1"])
    # Only the non-task scalar survives; every slot is gone (no orphans).
    assert mock_job.staged_metadata == {"dsi_validate_total_rows": 5}


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
