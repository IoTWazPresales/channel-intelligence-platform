"""Pipeline failure writeback uses a fresh session (dead-connection safe)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.ingestion.pipeline import STAGE_FAILED, process_import_job_sync


def test_pipeline_failure_writeback_uses_fresh_session() -> None:
    job_id = 77
    dead_session = MagicMock()
    dead_session.get.return_value = None

    pipeline_job = MagicMock()
    pipeline_job.template_slug = "distributor_inventory"
    pipeline_job.file_headers = None
    dead_session.scalar.return_value = pipeline_job

    fresh_job = MagicMock()
    fresh_job.id = job_id
    fresh_job.stage = "mapped"
    fresh_job.status = "running"

    fresh_session = MagicMock()
    fresh_session.get.return_value = fresh_job
    fresh_session.__enter__ = MagicMock(return_value=fresh_session)
    fresh_session.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.ingestion.pipeline.get_storage_backend", side_effect=RuntimeError("connection dropped")),
        patch("app.db.session_sync.SessionLocal", return_value=fresh_session),
        patch("app.ingestion.pipeline.persist_clear_background_task_metadata") as mock_clear,
    ):
        out = process_import_job_sync(dead_session, job_id)

    dead_session.rollback.assert_called_once()
    fresh_session.commit.assert_called_once()
    mock_clear.assert_called_once_with(fresh_session, fresh_job)
    assert fresh_job.status == "failed"
    assert fresh_job.stage == STAGE_FAILED
    assert "connection dropped" in (fresh_job.error_summary or "")
    assert isinstance(fresh_job.completed_at, datetime)
    assert out is fresh_job


def test_prepare_dsi_pipeline_dispatch_clears_stale_error_fields() -> None:
    from app.api.v1.endpoints.imports import _prepare_dsi_pipeline_dispatch
    from app.models.ingestion import ImportJob

    job = ImportJob(
        id=12,
        source_id=1,
        template_slug="distributor_inventory",
        file_name="x.csv",
        status="failed",
        stage="failed",
        error_summary="old pooler drop",
        completed_at=datetime.now(timezone.utc),
    )

    with patch(
        "app.api.v1.endpoints.imports.claim_import_pipeline_dispatch",
        return_value=job,
    ) as mock_claim:
        _prepare_dsi_pipeline_dispatch(12)

    mock_claim.assert_called_once_with(12, import_mode="validate")
