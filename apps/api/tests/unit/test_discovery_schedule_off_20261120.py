"""The listing-site autoconfigure schedule is a tenant setting, off by default."""

from __future__ import annotations

import contextlib

import pytest

from app.services import tenant_settings
from app.worker import tasks


class _Session:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def begin_nested(self):
        return contextlib.nullcontext()

    def execute(self, *_a, **_k):
        if self.fail:
            raise RuntimeError("relation tenant_setting does not exist")
        raise AssertionError("unexpected query")

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_unreadable_setting_reads_as_off() -> None:
    assert tenant_settings.tenants_with_true(_Session(fail=True), tenant_settings.KEY_DISCOVERY_SCHEDULE) == []


def test_unknown_key_and_non_bool_are_refused() -> None:
    with pytest.raises(ValueError):
        tenant_settings.set_setting(_Session(), "t", "no.such.key", True, actor="x")
    with pytest.raises(ValueError):
        tenant_settings.set_setting(_Session(), "t", tenant_settings.KEY_DISCOVERY_SCHEDULE, "yes", actor="x")


def _patch(monkeypatch, enabled: list[str]):
    calls: list[tuple[str | None, list[str] | None]] = []
    monkeypatch.setenv("CIP_ENABLE_DEV_BEAT", "1")
    monkeypatch.setattr("app.db.session_sync.SessionLocal", lambda: _Session())
    monkeypatch.setattr(tenant_settings, "tenants_with_true", lambda _s, _k: list(enabled))

    def fake_autoconfigure(_session, *, tenant_id=None, tenant_ids=None, http_get=None, **_kw):
        calls.append((tenant_id, tenant_ids))
        return {"configured": [], "excluded": [], "needs_pattern": [], "run": {"sites": []}}

    monkeypatch.setattr("app.services.listing_capture.autoconfig.autoconfigure_sites", fake_autoconfigure)
    return calls


def test_scheduled_run_does_nothing_when_no_tenant_switched_it_on(monkeypatch) -> None:
    calls = _patch(monkeypatch, [])
    result = tasks.listing_capture_autoconfigure_sites_task()
    assert result == {"skipped": True, "reason": "discovery_schedule_off"}
    assert calls == []


def test_scheduled_run_covers_only_enabled_tenants(monkeypatch) -> None:
    calls = _patch(monkeypatch, ["a", "b"])
    result = tasks.listing_capture_autoconfigure_sites_task()
    assert result["skipped"] is False
    # One shared call (one fetch policy, tenant rotation), narrowed to the enabled tenants.
    assert calls == [(None, ["a", "b"])]


def test_scheduled_run_for_a_tenant_that_is_off_is_skipped(monkeypatch) -> None:
    calls = _patch(monkeypatch, ["a"])
    result = tasks.listing_capture_autoconfigure_sites_task(tenant_id="b")
    assert result["skipped"] is True and calls == []


def test_on_demand_run_is_unchanged(monkeypatch) -> None:
    calls = _patch(monkeypatch, [])
    result = tasks.listing_capture_autoconfigure_sites_task(tenant_id="z", on_demand=True)
    assert result["skipped"] is False and calls == [("z", None)]


def test_beat_entry_is_still_registered_but_the_task_is_the_gate() -> None:
    from app.worker.celery_app import build_beat_schedule

    assert "listing-capture-autoconfigure" in build_beat_schedule()
