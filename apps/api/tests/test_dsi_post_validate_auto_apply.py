"""Tests for DSI post-validate auto-apply deferral (BACKLOG-040)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.imports.dsi_post_validate_auto_apply import (
    job_has_active_interactive_steward_tasks,
    schedule_or_enqueue_dsi_post_validate_auto_apply,
    try_flush_deferred_dsi_post_validate_auto_apply,
)
from app.services.imports.import_background_slots import (
    KIND_DSI_RESOLUTION_PLAN_COMPUTE,
    SLOT_DSI_BULK,
    set_task_slot_on_job,
)


def test_schedule_immediate_enqueue_when_defer_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CIP_DEFER_DSI_POST_VALIDATE_AUTO_APPLY", "0")
    job = MagicMock()
    job.id = 42
    job.staged_metadata = {}
    sync_db = MagicMock()

    with patch(
        "app.services.imports.dsi_post_validate_auto_apply.enqueue_dsi_resolution_plan_apply",
        return_value=("task-1", True),
    ) as enqueue:
        schedule_or_enqueue_dsi_post_validate_auto_apply(
            sync_db,
            job,
            candidate_ids=[1, 2],
            detach_from_caller=True,
        )

    enqueue.assert_called_once_with(42, {"candidate_ids": [1, 2]}, detach_from_caller=True)
    assert job.staged_metadata["dsi_post_validate_auto_apply"]["task_id"] == "task-1"


def test_schedule_defers_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("CIP_DEFER_DSI_POST_VALIDATE_AUTO_APPLY", "1")
    job = MagicMock()
    job.id = 7
    job.staged_metadata = {}
    sync_db = MagicMock()

    with patch("app.services.imports.dsi_post_validate_auto_apply.get_settings") as gs, patch(
        "app.services.imports.dsi_post_validate_auto_apply.celery_app.send_task"
    ) as send_task:
        gs.return_value.cip_dev_celery_dispatch = "broker"
        schedule_or_enqueue_dsi_post_validate_auto_apply(
            sync_db,
            job,
            candidate_ids=[9],
            detach_from_caller=True,
        )

    send_task.assert_called_once()
    assert job.staged_metadata["dsi_post_validate_auto_apply_deferred"]["candidate_ids"] == [9]


def test_schedule_defers_when_enabled_in_process_thread_flushes_sync(monkeypatch) -> None:
    """CI sets CIP_DEV_CELERY_DISPATCH=in_process_thread — defer path flushes without send_task."""
    monkeypatch.setenv("CIP_DEFER_DSI_POST_VALIDATE_AUTO_APPLY", "1")
    job = MagicMock()
    job.id = 7
    job.staged_metadata = {}
    sync_db = MagicMock()

    with patch("app.services.imports.dsi_post_validate_auto_apply.get_settings") as gs, patch(
        "app.services.imports.dsi_post_validate_auto_apply.celery_app.send_task"
    ) as send_task, patch(
        "app.services.imports.dsi_post_validate_auto_apply.try_flush_deferred_dsi_post_validate_auto_apply",
        return_value=True,
    ) as flush:
        gs.return_value.cip_dev_celery_dispatch = "in_process_thread"
        schedule_or_enqueue_dsi_post_validate_auto_apply(
            sync_db,
            job,
            candidate_ids=[9],
            detach_from_caller=True,
        )

    send_task.assert_not_called()
    flush.assert_called_once_with(sync_db, 7)
    sync_db.commit.assert_called_once()
    assert job.staged_metadata["dsi_post_validate_auto_apply_deferred"]["candidate_ids"] == [9]


def test_job_has_active_interactive_steward_tasks_pending() -> None:
    job = MagicMock()
    job.id = 1
    job.template_slug = "distributor_inventory"
    set_task_slot_on_job(
        job,
        SLOT_DSI_BULK,
        task_id="celery-task-abc",
        async_poll=True,
        kind=KIND_DSI_RESOLUTION_PLAN_COMPUTE,
    )
    sync_db = MagicMock()
    sync_db.get.return_value = job

    with patch(
        "app.services.imports.dsi_post_validate_auto_apply._read_celery_safe",
        return_value=("PENDING", {}),
    ):
        assert job_has_active_interactive_steward_tasks(sync_db, 1) is True


def test_flush_deferred_when_idle(monkeypatch) -> None:
    job = MagicMock()
    job.id = 5
    job.staged_metadata = {
        "dsi_post_validate_auto_apply_deferred": {"candidate_ids": [3, 4]},
    }
    sync_db = MagicMock()
    sync_db.get.return_value = job

    with patch(
        "app.services.imports.dsi_post_validate_auto_apply.job_has_active_interactive_steward_tasks",
        return_value=False,
    ), patch(
        "app.services.imports.dsi_post_validate_auto_apply.enqueue_dsi_resolution_plan_apply",
        return_value=("task-flush", True),
    ):
        assert try_flush_deferred_dsi_post_validate_auto_apply(sync_db, 5) is True

    assert "dsi_post_validate_auto_apply_deferred" not in job.staged_metadata
    assert job.staged_metadata["dsi_post_validate_auto_apply"]["task_id"] == "task-flush"
