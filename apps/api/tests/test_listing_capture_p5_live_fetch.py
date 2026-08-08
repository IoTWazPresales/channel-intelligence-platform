"""P5 listing live fetch: schedule env gate + worker task skip paths (mocked env/session)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.listing_capture.registry import (
    _listing_capture_schedule_enabled_from_env,
    scheduler_should_run,
)
from app.worker.tasks import _listing_live_fetch_enabled, listing_capture_poll_listings_task


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", True),
        ("true", True),
        ("True", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
    ],
)
def test_schedule_env_gate_truthy_parsing(monkeypatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("CIP_LISTING_CAPTURE_SCHEDULE", raw)
    assert _listing_capture_schedule_enabled_from_env() is expected


def test_schedule_env_gate_unset_defaults_disabled(monkeypatch) -> None:
    monkeypatch.delenv("CIP_LISTING_CAPTURE_SCHEDULE", raising=False)
    assert _listing_capture_schedule_enabled_from_env() is False


def test_scheduler_should_run_reads_live_env(monkeypatch) -> None:
    session = MagicMock()
    session.scalar.return_value = 2
    monkeypatch.setenv("CIP_LISTING_CAPTURE_SCHEDULE", "1")
    gate = scheduler_should_run(session)
    assert gate["should_run"] is True
    monkeypatch.setenv("CIP_LISTING_CAPTURE_SCHEDULE", "0")
    gate2 = scheduler_should_run(session)
    assert gate2["should_run"] is False


@pytest.mark.parametrize(
    "raw,expected",
    [("1", True), ("true", True), ("on", True), ("0", False), ("", False)],
)
def test_live_fetch_env_gate(monkeypatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", raw)
    assert _listing_live_fetch_enabled() is expected


def _fake_session_local(session: MagicMock) -> MagicMock:
    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory


def test_poll_task_skips_when_dev_beat_disabled(monkeypatch) -> None:
    monkeypatch.setattr("app.worker.celery_queues.dev_beat_disabled", lambda: True)
    out = listing_capture_poll_listings_task()
    assert out == {"skipped": True, "reason": "dev_beat_disabled"}


def test_poll_task_skips_when_schedule_gate_closed(monkeypatch) -> None:
    monkeypatch.setattr("app.worker.celery_queues.dev_beat_disabled", lambda: False)
    session = MagicMock()
    session.scalar.return_value = 0
    monkeypatch.setattr("app.db.session_sync.SessionLocal", _fake_session_local(session))
    monkeypatch.delenv("CIP_LISTING_CAPTURE_SCHEDULE", raising=False)
    out = listing_capture_poll_listings_task()
    assert out["skipped"] is True
    assert out["reason"] == "schedule_disabled_or_empty"
    assert out["should_run"] is False


def test_poll_task_skips_when_live_fetch_disabled(monkeypatch) -> None:
    monkeypatch.setattr("app.worker.celery_queues.dev_beat_disabled", lambda: False)
    session = MagicMock()
    session.scalar.return_value = 3
    monkeypatch.setattr("app.db.session_sync.SessionLocal", _fake_session_local(session))
    monkeypatch.setenv("CIP_LISTING_CAPTURE_SCHEDULE", "1")
    monkeypatch.delenv("CIP_LISTING_LIVE_FETCH", raising=False)
    out = listing_capture_poll_listings_task()
    assert out["skipped"] is True
    assert out["reason"] == "live_fetch_not_enabled"
    assert out["should_run"] is True


def test_poll_task_polls_active_listings_when_fully_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.worker.celery_queues.dev_beat_disabled", lambda: False)
    session = MagicMock()
    session.scalar.return_value = 1
    listing = MagicMock(id=1, url="https://example.com/p", marketplace="takealot", status="active")
    session.scalars.return_value.all.return_value = [listing]
    monkeypatch.setattr("app.db.session_sync.SessionLocal", _fake_session_local(session))
    monkeypatch.setenv("CIP_LISTING_CAPTURE_SCHEDULE", "1")
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")

    def fake_record_observation(_session, _listing, *, http_get=None):
        assert http_get is not None
        return MagicMock()

    monkeypatch.setattr("app.services.listing_capture.registry.record_observation", fake_record_observation)
    out = listing_capture_poll_listings_task()
    assert out["skipped"] is False
    assert out["polled"] == 1
    assert out["failed"] == 0
    assert out["listing_count"] == 1
