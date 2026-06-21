"""Import pipeline dispatch claim — busy guard, self-healing reclaim, and race safety."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import app.services.imports.import_pipeline_dispatch_claim as claim_mod
from app.services.imports.import_pipeline_dispatch_claim import (
    FRESH_DSI_CHECKPOINT_SECONDS,
    PIPELINE_DISPATCH_CLAIM_SECONDS,
    PipelineDispatchBusyError,
    claim_import_pipeline_dispatch_sync,
    dsi_validate_checkpoint_age_seconds,
    import_pipeline_dispatch_is_busy,
    raise_if_import_pipeline_busy,
    reclaim_stale_pipeline_dispatch_claim,
)


def _job(
    *,
    status: str = "running",
    checkpoint_at: str | None = None,
    queued_at: str | None = None,
    celery_task_id: str | None = None,
    jid: int = 7,
) -> SimpleNamespace:
    meta: dict = {}
    if checkpoint_at is not None:
        meta["dsi_validate_checkpoint_at"] = checkpoint_at
    if queued_at is not None:
        meta["pipeline_queued_at"] = queued_at
    if celery_task_id is not None:
        meta["celery_task_id"] = celery_task_id
    return SimpleNamespace(id=jid, status=status, staged_metadata=meta, import_mode="validate")


def _iso_seconds_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _patch_state(monkeypatch, value: str | None) -> None:
    monkeypatch.setattr(claim_mod, "read_main_celery_state", lambda job, **_k: value)


# --- checkpoint age ---------------------------------------------------------------------------


def test_checkpoint_age_none_when_absent() -> None:
    assert dsi_validate_checkpoint_age_seconds(_job()) is None


def test_checkpoint_age_recent() -> None:
    age = dsi_validate_checkpoint_age_seconds(_job(checkpoint_at=_iso_seconds_ago(5)))
    assert age is not None
    assert 0 <= age < 30


# --- import_pipeline_dispatch_is_busy ---------------------------------------------------------


def test_active_celery_blocks_regardless_of_job_status(monkeypatch) -> None:
    _patch_state(monkeypatch, "PROGRESS")
    assert import_pipeline_dispatch_is_busy(_job(status="validated", celery_task_id="t1")) is True


def test_fresh_pipeline_queued_at_blocks_without_celery(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    fresh = _iso_seconds_ago(PIPELINE_DISPATCH_CLAIM_SECONDS / 2)
    assert import_pipeline_dispatch_is_busy(_job(status="completed", queued_at=fresh)) is True


def test_lost_celery_with_fresh_checkpoint_blocks(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    fresh = _iso_seconds_ago(FRESH_DSI_CHECKPOINT_SECONDS / 2)
    assert import_pipeline_dispatch_is_busy(_job(status="running", checkpoint_at=fresh)) is True


def test_terminal_celery_does_not_block_even_with_fresh_checkpoint(monkeypatch) -> None:
    _patch_state(monkeypatch, "SUCCESS")
    assert (
        import_pipeline_dispatch_is_busy(
            _job(status="validated", checkpoint_at=_iso_seconds_ago(1), celery_task_id="t1")
        )
        is False
    )


def test_stale_checkpoint_and_queued_at_allow_dispatch(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    stale_cp = _iso_seconds_ago(FRESH_DSI_CHECKPOINT_SECONDS + 60)
    stale_q = _iso_seconds_ago(PIPELINE_DISPATCH_CLAIM_SECONDS + 60)
    assert import_pipeline_dispatch_is_busy(_job(status="running", checkpoint_at=stale_cp, queued_at=stale_q)) is False


def test_raise_if_busy_raises_409(monkeypatch) -> None:
    _patch_state(monkeypatch, "PENDING")
    with pytest.raises(HTTPException) as exc:
        raise_if_import_pipeline_busy(_job(status="validated", celery_task_id="t1"))
    assert exc.value.status_code == 409


# --- self-healing reclaim ---------------------------------------------------------------------


def test_reclaim_clears_terminal_celery_slot(monkeypatch) -> None:
    _patch_state(monkeypatch, "SUCCESS")
    job = _job(status="validated", celery_task_id="dead-task", queued_at=_iso_seconds_ago(600))
    session = MagicMock()
    assert reclaim_stale_pipeline_dispatch_claim(session, job) is True
    assert "celery_task_id" not in (job.staged_metadata or {})
    assert "pipeline_queued_at" not in (job.staged_metadata or {})


def test_reclaim_skips_while_active(monkeypatch) -> None:
    _patch_state(monkeypatch, "PROGRESS")
    job = _job(celery_task_id="live-task")
    session = MagicMock()
    assert reclaim_stale_pipeline_dispatch_claim(session, job) is False
    assert job.staged_metadata.get("celery_task_id") == "live-task"


# --- atomic claim (serialized FOR UPDATE) -----------------------------------------------------


def test_concurrent_claim_exactly_one_wins() -> None:
    """Two threads under one row lock: first claims, second gets PipelineDispatchBusyError."""
    from app.models.ingestion import ImportJob

    job = ImportJob(
        id=42,
        source_id=1,
        template_slug="distributor_inventory",
        file_name="x.csv",
        status="completed",
        stage="validated",
        import_mode="validate",
        staged_metadata={},
    )
    row_lock = threading.Lock()
    outcomes: list[str] = []

    class _FakeResult:
        def scalar_one_or_none(self):
            return job

    class _FakeSession:
        def execute(self, _stmt):
            row_lock.acquire()
            return _FakeResult()

        def add(self, _job):
            return None

        def flush(self):
            return None

        def commit(self):
            row_lock.release()

        def rollback(self):
            if row_lock.locked():
                row_lock.release()

    session = _FakeSession()

    def _attempt():
        try:
            with patch(
                "app.services.imports.import_pipeline_dispatch_claim.read_main_celery_state",
                return_value=None,
            ):
                claim_import_pipeline_dispatch_sync(session, 42, import_mode="validate")
            outcomes.append("claimed")
        except PipelineDispatchBusyError:
            outcomes.append("busy")
        finally:
            if row_lock.locked():
                row_lock.release()

    t1 = threading.Thread(target=_attempt)
    t2 = threading.Thread(target=_attempt)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert outcomes.count("claimed") == 1
    assert outcomes.count("busy") == 1
    assert job.status == "running"
    assert job.staged_metadata.get("pipeline_queued_at")
    assert job.staged_metadata.get("pipeline_dispatch_claim")


def test_claim_sets_running_and_dispatch_metadata(monkeypatch) -> None:
    from app.models.ingestion import ImportJob

    job = ImportJob(
        id=12,
        source_id=1,
        template_slug="distributor_inventory",
        file_name="x.csv",
        status="failed",
        stage="failed",
        error_summary="old error",
        completed_at=datetime.now(timezone.utc),
        import_mode="validate",
        staged_metadata={},
    )
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = job
    _patch_state(monkeypatch, None)

    out = claim_import_pipeline_dispatch_sync(session, 12, import_mode="validate")

    assert out is job
    assert job.status == "running"
    assert job.error_summary is None
    assert job.completed_at is None
    assert job.staged_metadata.get("pipeline_queued_at")
    assert job.staged_metadata.get("pipeline_dispatch_claim")
