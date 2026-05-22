"""Background task discovery (sync SessionLocal — active Celery states only)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.imports.background_tasks import list_active_import_background_tasks_sync
from app.services.imports.import_job_background_metadata import (
    ACTIVE_CELERY_STATES,
    clear_background_task_metadata,
)


def test_clear_background_task_metadata_strips_keys() -> None:
    meta = {"celery_task_id": "abc", "dsi_bulk_task": {"task_id": "x"}, "dsi_validate_total_rows": 10}
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
