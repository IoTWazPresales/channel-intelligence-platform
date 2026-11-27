"""Worker-start discovery is not skipped because beat is off. No database."""

from __future__ import annotations

from datetime import datetime, timezone


def test_startup_queues_when_beat_is_disabled(monkeypatch) -> None:
    # Warren 25 Nov: discovery runs when the services are up, not only at the next beat slot.
    from app.services.listing_capture import autoconfig_schedule as schedule

    queued: dict = {}

    def enqueue(*, kwargs, countdown=None):
        queued["kwargs"] = kwargs
        queued["countdown"] = countdown

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.db.session_sync.SessionLocal", lambda: _Session())
    monkeypatch.setattr(
        schedule,
        "due_scheduled_tenants",
        lambda session, store=None, now=None: (["default"], []),
    )
    monkeypatch.setattr(schedule, "note_scheduled_run", lambda **_kwargs: None)
    out = schedule._startup(
        enqueue=enqueue,
        store=None,
        now=datetime.now(timezone.utc),
        beat_disabled=True,
    )
    assert out == {"skipped": False, "queued": True, "tenants": 1}
    assert queued["kwargs"] == {"tenant_ids": ["default"], "startup": True}
