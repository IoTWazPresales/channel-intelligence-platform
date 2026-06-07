"""Background task discovery (sync SessionLocal — active Celery states only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.services.imports.background_tasks import list_active_import_background_tasks_sync
from app.services.imports.import_job_background_metadata import (
    ACTIVE_CELERY_STATES,
    TERMINAL_CELERY_STATES,
    clear_background_task_metadata,
)


def test_clear_background_task_metadata_strips_keys() -> None:
    meta = {
        "celery_task_id": "abc",
        "dsi_bulk_task": {"task_id": "x"},
        "dsi_validate_total_rows": 10,
        "pipeline_queued_at": "2026-01-01T00:00:00+00:00",
        "pipeline_started_at": "2026-01-01T00:00:01+00:00",
    }
    cleared = clear_background_task_metadata(meta)
    assert cleared == {"dsi_validate_total_rows": 10}


def test_list_active_import_background_tasks_uses_session_local() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = "completed"
    mock_job.template_slug = "distributor_inventory"
    mock_job.import_mode = "validate"
    mock_job.file_name = "test.csv"
    mock_job.staged_metadata = None

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with patch("app.services.imports.background_tasks.SessionLocal") as mock_local:
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    mock_local.assert_called_once()
    mock_session.scalars.assert_called_once()
    assert out == []


def test_terminal_celery_clears_metadata_and_is_not_listed() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 42
    mock_job.status = "completed"
    mock_job.template_slug = "distributor_inventory"
    mock_job.import_mode = "validate"
    mock_job.file_name = "test.csv"
    mock_job.staged_metadata = {"celery_task_id": "task-1"}

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch("app.services.imports.background_tasks.SessionLocal") as mock_local,
        patch("app.services.imports.background_tasks._read_celery", return_value=("SUCCESS", {})),
    ):
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    assert out == []
    assert mock_job.staged_metadata is None
    mock_session.commit.assert_called_once()


def test_progress_celery_state_is_active() -> None:
    assert "PROGRESS" in ACTIVE_CELERY_STATES
    assert "SUCCESS" not in ACTIVE_CELERY_STATES
    assert "SUCCESS" in TERMINAL_CELERY_STATES


def test_running_revalidate_on_validated_job_lists_active_task() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 733
    mock_job.status = "running"
    mock_job.stage = "validated"
    mock_job.template_slug = "distributor_inventory"
    mock_job.import_mode = "validate"
    mock_job.file_name = "test.csv"
    mock_job.staged_metadata = {"celery_task_id": "task-live", "dsi_validate_total_rows": 100}

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch("app.services.imports.background_tasks.SessionLocal") as mock_local,
        patch(
            "app.services.imports.background_tasks._read_celery_safe",
            return_value=("PROGRESS", {"phase": "processing_rows", "pct": 10, "current_row": 10, "total_rows": 100}),
        ),
    ):
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    assert len(out) == 1
    assert out[0]["import_job_id"] == 733
    assert out[0]["pct"] == 10


def test_pm_commit_in_progress_is_listed_in_activity_feed() -> None:
    """PM commit must surface in the global activity feed (bell) like other importers."""
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 4
    mock_job.status = "commit_running"
    mock_job.stage = "pm_validated"
    mock_job.template_slug = "product_master"
    mock_job.import_mode = "apply"
    mock_job.file_name = "catalog.xlsx"
    mock_job.staged_metadata = {
        "pm_commit_task": {
            "task_id": "commit-task-1",
            "kind": "product_master_commit",
            "label": "Committing product master…",
        }
    }

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch("app.services.imports.background_tasks.SessionLocal") as mock_local,
        patch(
            "app.services.imports.background_tasks._read_celery_safe",
            return_value=("PROGRESS", {"phase": "applying", "pct": 40}),
        ),
    ):
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    assert len(out) == 1
    assert out[0]["import_job_id"] == 4
    assert out[0]["kind"] == "product_master_commit"


def test_pm_commit_slot_cleared_once_job_completed() -> None:
    """A finished PM commit (stage pm_committed) drops out of the feed and clears its slot."""
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 4
    mock_job.status = "completed"
    mock_job.stage = "pm_committed"
    mock_job.template_slug = "product_master"
    mock_job.import_mode = "apply"
    mock_job.file_name = "catalog.xlsx"
    mock_job.staged_metadata = {"pm_commit_task": {"task_id": "commit-task-1"}}

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with patch("app.services.imports.background_tasks.SessionLocal") as mock_local:
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    assert out == []
    assert mock_job.staged_metadata is None
    mock_session.commit.assert_called_once()


def test_validated_job_clears_metadata_when_celery_still_pending() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 99
    mock_job.status = "completed_with_errors"
    mock_job.stage = "validated"
    mock_job.template_slug = "distributor_inventory"
    mock_job.import_mode = "validate"
    mock_job.file_name = "test.csv"
    mock_job.staged_metadata = {"celery_task_id": "task-stale", "dsi_validate_total_rows": 100}

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch("app.services.imports.background_tasks.SessionLocal") as mock_local,
        patch("app.services.imports.background_tasks._read_celery", return_value=("PENDING", {})),
    ):
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    assert out == []
    assert mock_job.staged_metadata == {"dsi_validate_total_rows": 100}
    mock_session.commit.assert_called_once()


def test_stale_pending_slot_cleared_after_dispatch_age() -> None:
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 43
    mock_job.status = "completed_with_errors"
    mock_job.stage = "validated"
    mock_job.template_slug = "distributor_inventory"
    mock_job.import_mode = "validate"
    mock_job.file_name = "test.csv"
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
    mock_job.staged_metadata = {
        "dsi_bulk_task": {
            "task_id": "task-stale-pending",
            "kind": "dsi_resolution_plan_apply",
            "async_poll": True,
            "queued_at": stale_at,
        }
    }
    mock_job.updated_at = datetime.now(timezone.utc) - timedelta(minutes=25)

    mock_session.scalars.return_value.all.return_value = [mock_job]

    with (
        patch("app.services.imports.background_tasks.SessionLocal") as mock_local,
        patch("app.services.imports.background_tasks._read_celery", return_value=("PENDING", {})),
    ):
        mock_local.return_value.__enter__.return_value = mock_session
        out = list_active_import_background_tasks_sync(limit=10)

    assert out == []
    assert not mock_job.staged_metadata
    mock_session.commit.assert_called_once()
