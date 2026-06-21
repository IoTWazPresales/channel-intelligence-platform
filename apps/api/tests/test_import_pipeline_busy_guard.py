"""Duplicate-dispatch guard: active Celery state OR a fresh DB checkpoint blocks re-validate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.services.imports.import_pipeline_dispatch_claim as claim_mod
from app.services.imports.import_pipeline_dispatch_claim import (
    FRESH_DSI_CHECKPOINT_SECONDS,
    dsi_validate_checkpoint_age_seconds,
    import_pipeline_dispatch_is_busy,
    raise_if_import_pipeline_busy,
)


def _job(
    *,
    status: str = "running",
    checkpoint_at: str | None = None,
    celery_task_id: str | None = None,
    jid: int = 7,
) -> SimpleNamespace:
    meta: dict = {}
    if checkpoint_at is not None:
        meta["dsi_validate_checkpoint_at"] = checkpoint_at
    if celery_task_id is not None:
        meta["celery_task_id"] = celery_task_id
    return SimpleNamespace(id=jid, status=status, staged_metadata=meta)


def _iso_seconds_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _patch_state(monkeypatch, value: str | None) -> None:
    monkeypatch.setattr(claim_mod, "read_main_celery_state", lambda job, **_k: value)


def test_checkpoint_age_none_when_absent() -> None:
    assert dsi_validate_checkpoint_age_seconds(_job()) is None


def test_checkpoint_age_none_when_unparseable() -> None:
    assert dsi_validate_checkpoint_age_seconds(_job(checkpoint_at="not-a-date")) is None


def test_checkpoint_age_naive_timestamp_treated_as_utc() -> None:
    naive = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None).isoformat()
    age = dsi_validate_checkpoint_age_seconds(_job(checkpoint_at=naive))
    assert age is not None
    assert 0 <= age < 30


def test_active_celery_state_blocks_even_when_not_running(monkeypatch) -> None:
    _patch_state(monkeypatch, "PROGRESS")
    with pytest.raises(HTTPException) as exc:
        raise_if_import_pipeline_busy(_job(status="validated", celery_task_id="t1"))
    assert exc.value.status_code == 409


def test_lost_state_with_fresh_checkpoint_blocks(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    fresh = _iso_seconds_ago(FRESH_DSI_CHECKPOINT_SECONDS / 2)
    with pytest.raises(HTTPException) as exc:
        raise_if_import_pipeline_busy(_job(status="running", checkpoint_at=fresh))
    assert exc.value.status_code == 409


def test_lost_state_with_stale_checkpoint_allows_dispatch(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    stale = _iso_seconds_ago(FRESH_DSI_CHECKPOINT_SECONDS + 60)
    assert import_pipeline_dispatch_is_busy(_job(status="running", checkpoint_at=stale)) is False


def test_terminal_state_does_not_block_even_with_fresh_checkpoint(monkeypatch) -> None:
    _patch_state(monkeypatch, "SUCCESS")
    assert (
        import_pipeline_dispatch_is_busy(
            _job(status="running", checkpoint_at=_iso_seconds_ago(1), celery_task_id="t1")
        )
        is False
    )
