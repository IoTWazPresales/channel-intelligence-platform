"""Activation timing alerts (W1-B; Warren 2026-11-18: 3 days late or early). No DB."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.services.listing_capture.intelligence_v1 import (
    activation_timing,
    build_listing_intelligence,
)

START = date(2026, 11, 1)
END = date(2026, 11, 30)


def _obs(day: int, status: str, *, start=START, end=END, case_id=7, i=0):
    on = START + timedelta(days=day)
    return SimpleNamespace(
        id=i or day + 1,
        fetched_at=datetime(on.year, on.month, on.day, 9, tzinfo=UTC),
        extracted_price=999.0,
        parse_flags={
            "cpor_activation": {
                "status": status,
                "as_of": on.isoformat(),
                "case_id": case_id,
                "case_code": f"CASE-{case_id}",
                "line_window_start": start.isoformat(),
                "line_window_end": end.isoformat(),
                "case_price": 999.0,
            }
        },
    )


OFF, AT = "not_activated", "price_consistent"


def test_live_within_the_threshold_raises_nothing():
    assert activation_timing([_obs(0, OFF), _obs(1, AT), _obs(29, AT)], alert_days=3) == []


def test_still_off_price_three_days_in_is_late():
    alerts = activation_timing([_obs(0, OFF), _obs(3, OFF), _obs(5, AT)], alert_days=3)
    assert len(alerts) == 1
    late = alerts[0]
    assert late["kind"] == "late_activation"
    assert late["not_at_price_on"] == "2026-11-04"
    assert late["at_price_from"] == "2026-11-06"
    assert late["days_late_at_least"] == 3
    assert late["alert_days"] == 3 and late["case_code"] == "CASE-7"


def test_only_a_check_proves_lateness():
    # Off on day 2, at price on day 4: it may have gone live on day 2 or 3, so not proven late.
    reads = [_obs(2, OFF), _obs(4, AT)]
    assert activation_timing(reads, alert_days=3) == []
    assert activation_timing(reads, alert_days=2)[0]["days_late_at_least"] == 2


def test_never_activated_is_late_with_no_live_date():
    late = activation_timing([_obs(10, OFF), _obs(12, OFF)], alert_days=3)
    assert [a["kind"] for a in late] == ["late_activation"]
    assert late[0]["at_price_from"] is None
    assert late[0]["days_late_at_least"] == 12  # the latest check that proves it


def test_off_price_well_before_the_end_is_early():
    alerts = activation_timing(
        [_obs(0, AT), _obs(10, AT), _obs(20, OFF), _obs(24, AT)], alert_days=3
    )
    assert len(alerts) == 1
    early = alerts[0]
    assert early["kind"] == "early_deactivation"
    assert early["last_at_price_on"] == "2026-11-11"
    assert early["off_price_on"] == "2026-11-21"
    assert early["back_at_price_on"] == "2026-11-25"
    assert early["days_early_at_least"] == 9


def test_leaving_the_price_inside_the_last_days_is_not_early():
    # Off on 28 Nov, two days before a 30 Nov end.
    assert activation_timing([_obs(0, AT), _obs(27, OFF)], alert_days=3) == []
    assert (
        activation_timing([_obs(0, AT), _obs(26, OFF)], alert_days=3)[0]["days_early_at_least"] == 3
    )


def test_other_statuses_and_reads_outside_the_window_are_ignored():
    stray = _obs(5, OFF)
    stray.parse_flags["cpor_activation"]["status"] = "no_case_detected"
    outside = _obs(5, OFF, start=date(2026, 12, 1), end=date(2026, 12, 31))
    assert (
        activation_timing([stray, outside, SimpleNamespace(parse_flags=None)], alert_days=3) == []
    )


def test_each_window_is_judged_on_its_own():
    other_start, other_end = date(2026, 11, 10), date(2026, 11, 20)
    reads = [
        _obs(0, AT),
        _obs(15, OFF, start=other_start, end=other_end, case_id=8, i=100),
        _obs(29, AT),
    ]
    alerts = activation_timing(reads, alert_days=3)
    assert [(a["case_id"], a["kind"]) for a in alerts] == [(8, "late_activation")]


def _session(observations):
    listing = SimpleNamespace(
        id=4, customer_id=11, product_id=9, marketplace="shop-a", url="u", external_id="x"
    )
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [listing]),
        MagicMock(all=lambda: observations),
    ]
    return session


def test_intelligence_uses_the_configured_threshold(monkeypatch: pytest.MonkeyPatch):
    import app.services.listing_capture.intelligence_v1 as mod

    reads = [_obs(0, OFF), _obs(4, OFF), _obs(6, AT)]
    monkeypatch.setattr(mod, "_alert_days", lambda: 3)
    out = build_listing_intelligence(_session(reads))
    assert out["activation_alert_days"] == 3
    assert out["late_activation_count"] == 1 and out["early_deactivation_count"] == 0
    assert out["timing_alerts"][0]["listing_id"] == 4
    assert out["items"][0]["activation_timing"][0]["kind"] == "late_activation"

    monkeypatch.setattr(mod, "_alert_days", lambda: 5)
    assert build_listing_intelligence(_session(reads))["timing_alerts"] == []
    assert build_listing_intelligence(_session(reads), alert_days=4)["late_activation_count"] == 1


def test_the_setting_defaults_to_three_and_reads_the_environment(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import Settings

    base = {"database_url": "postgresql+asyncpg://u@h/x", "database_url_sync": "postgresql://u@h/x"}
    monkeypatch.delenv("CIP_LISTING_ACTIVATION_ALERT_DAYS", raising=False)
    assert Settings(_env_file=None, **base).cip_listing_activation_alert_days == 3
    monkeypatch.setenv("CIP_LISTING_ACTIVATION_ALERT_DAYS", "5")
    assert Settings(_env_file=None, **base).cip_listing_activation_alert_days == 5
    monkeypatch.setenv("CIP_LISTING_ACTIVATION_ALERT_DAYS", "-1")
    with pytest.raises(ValueError):
        Settings(_env_file=None, **base)
