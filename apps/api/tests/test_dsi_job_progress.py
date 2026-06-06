"""GET /imports/jobs/{id}/dsi-progress — DB vs Celery authority."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.endpoints.imports import get_dsi_job_progress


def test_dsi_progress_returns_complete_when_db_validated_despite_stale_celery() -> None:
    async def _run() -> None:
        job = MagicMock()
        job.stage = "validated"
        job.status = "completed_with_errors"
        job.import_mode = "validate"
        job.staged_metadata = {"celery_task_id": "stale-task", "dsi_validate_total_rows": 500}

        db = AsyncMock()
        db.get = AsyncMock(return_value=job)

        with patch("app.services.imports.background_tasks.read_celery_with_timeout") as mock_read:
            mock_read.return_value = ("PROGRESS", {"phase": "processing_rows", "pct": 50})

            out = await get_dsi_job_progress(job_id=12, db=db)

        mock_read.assert_not_called()
        assert out["phase"] == "complete"
        assert out["status"] == "complete"
        assert out["phase_label"] == "Validation complete"
        assert out["pct"] == 100

    asyncio.run(_run())


def test_dsi_progress_apply_complete_label_when_loaded() -> None:
    async def _run() -> None:
        job = MagicMock()
        job.stage = "loaded"
        job.status = "completed"
        job.import_mode = "apply"
        job.staged_metadata = {"celery_task_id": "done-task", "dsi_validate_total_rows": 500}

        db = AsyncMock()
        db.get = AsyncMock(return_value=job)

        with patch("app.services.imports.background_tasks.read_celery_with_timeout") as mock_read:
            out = await get_dsi_job_progress(job_id=12, db=db)

        mock_read.assert_not_called()
        assert out["phase_label"] == "Apply complete"

    asyncio.run(_run())


def test_dsi_progress_returns_celery_when_revalidate_running_on_validated_job() -> None:
    async def _run() -> None:
        job = MagicMock()
        job.stage = "validated"
        job.status = "running"
        job.staged_metadata = {"celery_task_id": "active-task", "dsi_validate_total_rows": 1000}

        db = AsyncMock()
        db.get = AsyncMock(return_value=job)

        with patch("app.services.imports.background_tasks.read_celery_with_timeout") as mock_read:
            mock_read.return_value = (
                "PROGRESS",
                {
                    "phase": "processing_rows",
                    "phase_label": "Processing rows",
                    "current_row": 200,
                    "total_rows": 1000,
                    "pct": 20,
                },
            )

            out = await get_dsi_job_progress(job_id=12, db=db)

        mock_read.assert_called_once()
        assert out["phase"] == "processing_rows"
        assert out["pct"] == 20
        assert out["current_row"] == 200

    asyncio.run(_run())
