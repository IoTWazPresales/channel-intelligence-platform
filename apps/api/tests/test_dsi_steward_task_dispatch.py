"""Tests for DSI steward background dispatch helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.imports.dsi_steward_task_dispatch import reusable_dsi_bulk_task_id


def test_reusable_dsi_bulk_task_id_returns_active_compute_task() -> None:
    job = MagicMock()
    job.staged_metadata = {
        "dsi_bulk_task": {
            "task_id": "compute-abc",
            "kind": "dsi_resolution_plan_compute",
        }
    }
    with patch(
        "app.services.imports.dsi_steward_task_dispatch.read_dsi_bulk_celery_state",
        return_value="STARTED",
    ):
        assert reusable_dsi_bulk_task_id(job, kind="dsi_resolution_plan_compute") == "compute-abc"


def test_reusable_dsi_bulk_task_id_none_when_kind_differs() -> None:
    job = MagicMock()
    job.staged_metadata = {
        "dsi_bulk_task": {
            "task_id": "apply-abc",
            "kind": "dsi_resolution_plan_apply",
        }
    }
    with patch(
        "app.services.imports.dsi_steward_task_dispatch.read_dsi_bulk_celery_state",
        return_value="STARTED",
    ):
        assert reusable_dsi_bulk_task_id(job, kind="dsi_resolution_plan_compute") is None


def test_reusable_dsi_bulk_task_id_none_when_terminal() -> None:
    job = MagicMock()
    job.staged_metadata = {
        "dsi_bulk_task": {
            "task_id": "compute-done",
            "kind": "dsi_resolution_plan_compute",
        }
    }
    with patch(
        "app.services.imports.dsi_steward_task_dispatch.read_dsi_bulk_celery_state",
        return_value="SUCCESS",
    ):
        assert reusable_dsi_bulk_task_id(job, kind="dsi_resolution_plan_compute") is None
