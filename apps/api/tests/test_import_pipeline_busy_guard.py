"""Duplicate-dispatch guard: active Celery state OR a fresh DB checkpoint blocks re-validate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.services.imports.import_job_background_metadata as meta_mod
from app.api.v1.endpoints.imports import (
    _FRESH_DSI_CHECKPOINT_SECONDS,
    _dsi_validate_checkpoint_age_seconds,
    _raise_if_import_pipeline_busy,
)


def _job(*, status: str = "running", checkpoint_at: str | None = None, jid: int = 7) -> SimpleNamespace:
    meta: dict = {}
    if checkpoint_at is not None:
        meta["dsi_validate_checkpoint_at"] = checkpoint_at
    return SimpleNamespace(id=jid, status=status, staged_metadata=meta)


def _iso_seconds_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _patch_state(monkeypatch, value: str | None) -> None:
    monkeypatch.setattr(meta_mod, "read_main_celery_state", lambda job, **_k: value)


# --- _dsi_validate_checkpoint_age_seconds ------------------------------------------------------

def test_checkpoint_age_none_when_absent() -> None:
    assert _dsi_validate_checkpoint_age_seconds(_job()) is None


def test_checkpoint_age_none_when_unparseable() -> None:
    assert _dsi_validate_checkpoint_age_seconds(_job(checkpoint_at="not-a-date")) is None


def test_checkpoint_age_recent() -> None:
    age = _dsi_validate_checkpoint_age_seconds(_job(checkpoint_at=_iso_seconds_ago(5)))
    assert age is not None
    assert 0 <= age < 30


def test_checkpoint_age_naive_timestamp_treated_as_utc() -> None:
    naive = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None).isoformat()
    age = _dsi_validate_checkpoint_age_seconds(_job(checkpoint_at=naive))
    assert age is not None
    assert 0 <= age < 30


# --- _raise_if_import_pipeline_busy -----------------------------------------------------------

def test_not_running_never_blocks(monkeypatch) -> None:
    _patch_state(monkeypatch, "PROGRESS")
    # Even with an active Celery state and a fresh checkpoint, a non-running job is dispatchable.
    _raise_if_import_pipeline_busy(_job(status="validated", checkpoint_at=_iso_seconds_ago(1)))


def test_active_celery_state_blocks(monkeypatch) -> None:
    _patch_state(monkeypatch, "PROGRESS")
    with pytest.raises(HTTPException) as exc:
        _raise_if_import_pipeline_busy(_job(status="running"))
    assert exc.value.status_code == 409


def test_lost_state_with_fresh_checkpoint_blocks(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    fresh = _iso_seconds_ago(_FRESH_DSI_CHECKPOINT_SECONDS / 2)
    with pytest.raises(HTTPException) as exc:
        _raise_if_import_pipeline_busy(_job(status="running", checkpoint_at=fresh))
    assert exc.value.status_code == 409


def test_lost_state_with_stale_checkpoint_allows_dispatch(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    stale = _iso_seconds_ago(_FRESH_DSI_CHECKPOINT_SECONDS + 60)
    _raise_if_import_pipeline_busy(_job(status="running", checkpoint_at=stale))


def test_lost_state_with_no_checkpoint_allows_dispatch(monkeypatch) -> None:
    _patch_state(monkeypatch, None)
    _raise_if_import_pipeline_busy(_job(status="running"))


def test_terminal_state_does_not_block_even_with_fresh_checkpoint(monkeypatch) -> None:
    # SUCCESS is a real (non-None) terminal state — the fresh-checkpoint fallback must not fire,
    # so a just-finished job with a leftover recent checkpoint is still re-dispatchable.
    _patch_state(monkeypatch, "SUCCESS")
    _raise_if_import_pipeline_busy(_job(status="running", checkpoint_at=_iso_seconds_ago(1)))
