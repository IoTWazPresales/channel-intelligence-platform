"""Tests must not reach the live Celery broker (N-0111: a test task ran on the always-on worker)."""

from __future__ import annotations

import os

import pytest


def test_celery_app_uses_memory_transport_in_tests() -> None:
    if os.environ.get("CIP_TESTS_ALLOW_LIVE_BROKER") == "1":
        pytest.skip("live broker explicitly allowed for this run")
    from app.core.config import get_settings
    from app.worker.celery_app import celery_app

    settings = get_settings()
    assert settings.celery_broker_url.startswith("memory://")
    assert not settings.celery_result_backend.startswith("redis")
    assert str(celery_app.conf.broker_url).startswith("memory://")
    assert not str(celery_app.conf.result_backend or "").startswith("redis")


def test_sending_a_task_stays_in_process() -> None:
    if os.environ.get("CIP_TESTS_ALLOW_LIVE_BROKER") == "1":
        pytest.skip("live broker explicitly allowed for this run")
    from app.worker.celery_app import celery_app

    # Would have been picked up by the real worker before; now it only lands on the memory transport.
    result = celery_app.send_task("reports.fanout_import_complete", args=[0, 0])
    assert result.id
    with celery_app.connection_for_write() as conn:
        assert conn.transport_cls == "memory" or "memory" in str(conn.as_uri())
