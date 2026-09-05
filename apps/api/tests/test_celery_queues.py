"""Tests for Celery queue routing and dev beat flags (BACKLOG-038/039)."""

from __future__ import annotations

import sys

import pytest

from app.worker.celery_queues import (
    CELERY_QUEUE_BATCH,
    CELERY_QUEUE_INTERACTIVE,
    dev_beat_disabled,
    queue_for_task,
    worker_queue_subscription,
)


def test_interactive_tasks_route_to_interactive_queue() -> None:
    assert queue_for_task("imports.dsi_resolution_plan_compute") == CELERY_QUEUE_INTERACTIVE
    assert queue_for_task("imports.dsi_resolution_plan_apply") == CELERY_QUEUE_INTERACTIVE


def test_batch_tasks_route_to_batch_queue() -> None:
    assert queue_for_task("imports.process_job") == CELERY_QUEUE_BATCH
    assert queue_for_task("imports.reap_stale_running_jobs") == CELERY_QUEUE_BATCH
    assert queue_for_task("cpor.fetch_daily_fx_rate") == CELERY_QUEUE_BATCH


def test_worker_queue_subscription_interactive_first() -> None:
    assert worker_queue_subscription().startswith("interactive,")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows solo default")
def test_dev_beat_disabled_by_default_on_windows(monkeypatch) -> None:
    monkeypatch.delenv("CIP_ENABLE_DEV_BEAT", raising=False)
    monkeypatch.delenv("CIP_DISABLE_DEV_BEAT", raising=False)
    monkeypatch.delenv("CIP_CELERY_WORKER_POOL", raising=False)
    assert dev_beat_disabled() is True


def test_dev_beat_can_be_enabled_on_windows(monkeypatch) -> None:
    monkeypatch.setenv("CIP_ENABLE_DEV_BEAT", "1")
    assert dev_beat_disabled() is False


def test_dev_beat_explicit_disable(monkeypatch) -> None:
    monkeypatch.setenv("CIP_DISABLE_DEV_BEAT", "1")
    assert dev_beat_disabled() is True


def test_reap_skipped_when_dev_beat_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CIP_DISABLE_DEV_BEAT", "1")
    from app.worker.tasks import reap_stale_running_jobs_task

    out = reap_stale_running_jobs_task()
    assert out == {"skipped": True, "reason": "dev_beat_disabled"}
