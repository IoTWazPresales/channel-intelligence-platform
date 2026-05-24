"""Pipeline queued/started metadata on import jobs."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.imports.import_job_background_metadata import (
    clear_background_task_metadata,
    persist_pipeline_queued_at,
    persist_pipeline_worker_started_at,
)


def test_persist_pipeline_queued_at_sets_timestamp() -> None:
    job = MagicMock()
    job.staged_metadata = {}
    session = MagicMock()
    persist_pipeline_queued_at(session, job)
    assert "pipeline_queued_at" in job.staged_metadata
    assert job.staged_metadata.get("pipeline_started_at") is None
    session.add.assert_called_once_with(job)


def test_persist_pipeline_worker_started_at_only_once() -> None:
    job = MagicMock()
    job.staged_metadata = {"pipeline_started_at": "2026-01-01T00:00:01+00:00"}
    session = MagicMock()
    persist_pipeline_worker_started_at(session, job)
    session.add.assert_not_called()
