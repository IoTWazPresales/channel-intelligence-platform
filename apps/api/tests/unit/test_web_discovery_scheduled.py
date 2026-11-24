"""Scheduled Discovery V2 reporting run (beat path)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.listing_capture.web_discovery import preview as web_preview
from app.services.listing_capture.web_discovery import scheduled


def test_scheduled_skips_when_live_fetch_off(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.scheduled.listing_live_fetch_enabled", lambda: False
    )
    out = scheduled.run_scheduled_reporting_discovery(MagicMock(), tenant_id="t-a")
    assert out == {"skipped": True, "reason": "live_fetch_off"}


def test_scheduled_skips_when_discovery_settings_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.scheduled.listing_live_fetch_enabled", lambda: True
    )
    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.scheduled.load_discovery_settings",
        lambda _s, _t: type("S", (), {"missing_for": lambda _self, _scope: ["tenant.country"]})(),
    )
    out = scheduled.run_scheduled_reporting_discovery(MagicMock(), tenant_id="t-a")
    assert out["skipped"] is True and out["reason"] == "settings_missing"


def test_scheduled_reporting_preview_then_apply(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.scheduled.listing_live_fetch_enabled", lambda: True
    )
    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.scheduled.load_discovery_settings",
        lambda _s, _t: type("S", (), {"missing_for": lambda _self, _scope: []})(),
    )
    store = web_preview.MemoryPlanStore()
    calls: list[dict] = []

    def fake_preview(_session, **kwargs):
        calls.append(kwargs["request"])
        pid = kwargs["preview_id"]
        plan = web_preview.new_plan(kwargs["tenant_id"], pid, kwargs["request"])
        plan["status"] = web_preview.STATUS_DONE
        store.save(kwargs["tenant_id"], pid, plan)

    monkeypatch.setattr("app.services.listing_capture.web_discovery.scheduled.web_preview.run_preview", fake_preview)
    applied = {"sites_confirmed": 1}

    def fake_apply(_session, _store, **kwargs):
        return applied

    monkeypatch.setattr("app.services.listing_capture.web_discovery.scheduled.web_apply.apply_plan", fake_apply)

    session = MagicMock()
    out = scheduled.run_scheduled_reporting_discovery(
        session, tenant_id="t-a", plan_store=store, getter=MagicMock()
    )
    assert calls == [{"scope": "reporting"}]
    assert out["skipped"] is False and out["applied"] == applied
    session.rollback.assert_called_once()


def test_autoconfigure_calls_scheduled_web_discovery_on_beat_path(monkeypatch) -> None:
    from app.services.listing_capture import autoconfig

    monkeypatch.setattr(autoconfig, "_advisory_lock", lambda *_a: None)
    monkeypatch.setattr(autoconfig, "_tenant_ids", lambda *_a: ["t-a"])
    monkeypatch.setattr(autoconfig, "_site_run_summary", lambda *_a: [])
    monkeypatch.setattr(autoconfig, "_configure_tenant", lambda *_a, **_k: [])
    monkeypatch.setattr(autoconfig, "save_run_state", lambda *_a, **_k: None)
    monkeypatch.setattr(autoconfig, "load_run_state", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.services.listing_capture.observation.listing_live_fetch_enabled", lambda: True
    )
    monkeypatch.setattr(
        "app.services.listing_capture.discovery.discover_reporting_customers",
        lambda *_a, **_k: {"customers": []},
    )
    scheduled_calls: list[str] = []

    def fake_scheduled(_session, *, tenant_id: str):
        scheduled_calls.append(tenant_id)
        return {"skipped": False}

    monkeypatch.setattr(
        "app.services.listing_capture.web_discovery.scheduled.run_scheduled_reporting_discovery",
        fake_scheduled,
    )
    autoconfig.autoconfigure_sites(MagicMock(), tenant_ids=["t-a"], http_get=lambda *_a: (200, ""))
    assert scheduled_calls == ["t-a"]
    autoconfig.autoconfigure_sites(MagicMock(), tenant_id="t-a", http_get=lambda *_a: (200, ""))
    assert scheduled_calls == ["t-a"]