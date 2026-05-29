"""Regression tests for Product Master commit dispatch helpers (Celery / dev thread)."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_run_product_master_commit_job_invokes_worker_with_session() -> None:
    from app.worker.tasks import run_product_master_commit_job

    mock_db = MagicMock()
    with patch("app.db.session_sync.SessionLocal") as m_sl:
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_db
        ctx.__exit__.return_value = None
        m_sl.return_value = ctx
        with patch("app.services.imports.product_master_workflow.run_pm_commit_worker") as m_rw:
            jid = run_product_master_commit_job(42, False, celery_task_id="unit-test-id")
            assert jid == 42
            m_rw.assert_called_once()
            args, kwargs = m_rw.call_args
            assert args[0] is mock_db
            assert args[1] == 42
            assert kwargs["confirm_destructive"] is False
            assert kwargs["celery_task_id"] == "unit-test-id"


def test_run_product_master_commit_job_propagates_errors() -> None:
    from app.worker.tasks import run_product_master_commit_job

    mock_db = MagicMock()
    with patch("app.db.session_sync.SessionLocal") as m_sl:
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_db
        ctx.__exit__.return_value = None
        m_sl.return_value = ctx
        with patch(
            "app.services.imports.product_master_workflow.run_pm_commit_worker",
            side_effect=RuntimeError("commit boom"),
        ):
            with pytest.raises(RuntimeError, match="commit boom"):
                run_product_master_commit_job(7, True, celery_task_id="x")


def test_run_product_master_commit_job_logs_dev_only_execution(caplog: pytest.LogCaptureFixture) -> None:
    from app.worker.tasks import run_product_master_commit_job

    mock_db = MagicMock()
    with patch("app.db.session_sync.SessionLocal") as m_sl:
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_db
        ctx.__exit__.return_value = None
        m_sl.return_value = ctx
        with patch("app.services.imports.product_master_workflow.run_pm_commit_worker"):
            with caplog.at_level(logging.WARNING, logger="cip.dev_celery"):
                run_product_master_commit_job(99, False, celery_task_id="dev-in-process-thread")
    assert "DEV ONLY" in caplog.text or "in-process" in caplog.text.lower()
    assert "99" in caplog.text


def test_run_product_master_validate_job_invokes_worker_with_session() -> None:
    from app.worker.tasks import run_product_master_validate_job

    with patch("app.services.imports.pm_validate_sync.run_product_master_validate_sync", return_value=42) as m_run:
        jid = run_product_master_validate_job(42, celery_task_id="unit-test-id")
        assert jid == 42
        m_run.assert_called_once_with(42, celery_task_id="unit-test-id")


def test_startup_warns_when_in_process_thread_dispatch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("CIP_DEV_CELERY_DISPATCH", "in_process_thread")
    get_settings.cache_clear()
    try:
        with caplog.at_level(logging.WARNING, logger="cip.dev_celery"):
            with TestClient(app):
                pass
        assert "CIP_DEV_CELERY_DISPATCH=in_process_thread" in caplog.text
        assert "DEV ONLY" in caplog.text
    finally:
        monkeypatch.delenv("CIP_DEV_CELERY_DISPATCH", raising=False)
        get_settings.cache_clear()
