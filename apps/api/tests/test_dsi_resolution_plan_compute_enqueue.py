"""Unit tests for DSI resolution plan compute enqueue."""

from __future__ import annotations

from unittest.mock import patch

from app.services.imports.dsi_resolution_plan_enqueue import enqueue_dsi_resolution_plan_compute


def test_enqueue_resolution_plan_compute_dev_thread() -> None:
    payload = {"candidate_ids": [1, 2], "default_region_id": None, "default_channel_id": None}
    plan = {"import_job_id": 43, "rows": [], "summary": {"total": 0, "ready": 0, "not_ready": 0}}

    with patch("app.services.imports.dsi_resolution_plan_enqueue.celery_app") as celery:
        celery.send_task.side_effect = RuntimeError("no broker")
        with patch("app.services.imports.dsi_resolution_plan_enqueue.get_settings") as gs:
            gs.return_value.cip_dev_celery_dispatch = "in_process_thread"
            with patch(
                "app.services.imports.dsi_resolution_plan_enqueue.run_dsi_resolution_plan_compute_sync",
                return_value=plan,
            ):
                task_id, async_poll = enqueue_dsi_resolution_plan_compute(43, payload)

    assert async_poll is True
    assert task_id.startswith("dev-plan-compute-")
