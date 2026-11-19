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


def _obs(
    day: int, status: str, *, start=START, end=END, case_id=7, i=0, hour=9, basis="promo"
):
    on = START + timedelta(days=day)
    return SimpleNamespace(
        id=i or day + 1,
        fetched_at=datetime(on.year, on.month, on.day, hour, tzinfo=UTC),
        extracted_price=999.0,
        parse_flags={
            "cpor_activation": {
                "status": status,
                "price_basis": basis,
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


def test_a_failed_check_proves_nothing():
    # An error page that parsed to a price is evaluated by the poller; it must not count.
    err = _obs(5, OFF)
    err.http_status = 503
    flagged = _obs(6, OFF)
    flagged.parse_flags["snapshot_stored"] = "fetch_failed"
    unparsed = _obs(7, OFF)
    unparsed.parse_status = "parse_failed"
    assert activation_timing([_obs(0, AT), err, flagged, unparsed], alert_days=3) == []
    assert activation_timing([err, flagged, unparsed], alert_days=3) == []
    ok = _obs(5, OFF)
    ok.http_status, ok.parse_status = 200, "ok"
    assert [a["kind"] for a in activation_timing([ok], alert_days=3)] == ["late_activation"]


def test_late_activation_before_a_same_day_activation():
    alerts = activation_timing([_obs(3, OFF, hour=9), _obs(3, AT, hour=15)], alert_days=3)
    assert [a["kind"] for a in alerts] == ["late_activation"]
    assert alerts[0]["not_at_price_on"] == "2026-11-04"
    assert alerts[0]["at_price_from"] == "2026-11-04"
    assert alerts[0]["days_late_at_least"] == 3


def test_early_deactivation_on_the_first_activation_day():
    alerts = activation_timing([_obs(9, AT, hour=9), _obs(9, OFF, hour=15)], alert_days=3)
    assert [a["kind"] for a in alerts] == ["early_deactivation"]
    assert alerts[0]["last_at_price_on"] == "2026-11-10"
    assert alerts[0]["off_price_on"] == "2026-11-10"
    assert alerts[0]["back_at_price_on"] is None
    assert alerts[0]["days_early_at_least"] == 20


def test_same_day_recovery_is_after_the_off_price_check():
    reads = [
        _obs(0, AT),
        _obs(9, AT, hour=9),
        _obs(9, OFF, hour=15),
        _obs(9, AT, hour=18),
    ]
    (early,) = activation_timing(reads, alert_days=3)
    assert early["kind"] == "early_deactivation"
    assert early["last_at_price_on"] == "2026-11-10"
    assert early["off_price_on"] == "2026-11-10"
    assert early["back_at_price_on"] == "2026-11-10"


def test_equal_fetch_times_keep_the_callers_id_order():
    reads = [_obs(3, status, i=i) for i, status in enumerate((OFF, AT, OFF, AT), start=1)]
    alerts = activation_timing(reads, alert_days=3)
    assert [a["kind"] for a in alerts] == ["early_deactivation", "late_activation"]
    early, late = alerts
    assert early["back_at_price_on"] == late["at_price_from"] == "2026-11-04"
    assert early["days_early_at_least"] == 26
    assert late["days_late_at_least"] == 3


def test_same_day_check_before_activation_is_not_early_deactivation():
    # The morning check is below the late threshold and precedes the first activation.
    assert activation_timing([_obs(2, OFF, hour=9), _obs(2, AT, hour=15)], alert_days=3) == []


@pytest.mark.parametrize("day, expected", [(2, []), (3, ["late_activation"])])
def test_same_day_late_threshold_uses_calendar_days(day, expected):
    reads = [_obs(day, OFF, hour=9), _obs(day, AT, hour=10)]
    assert [a["kind"] for a in activation_timing(reads, alert_days=3)] == expected


@pytest.mark.parametrize("day, expected", [(26, ["early_deactivation"]), (27, [])])
def test_same_day_early_threshold_uses_calendar_days(day, expected):
    reads = [_obs(day, AT, hour=9), _obs(day, OFF, hour=10)]
    assert [a["kind"] for a in activation_timing(reads, alert_days=3)] == expected


def test_zero_day_threshold_keeps_same_day_transitions():
    reads = [_obs(0, OFF, hour=9), _obs(0, AT, hour=12), _obs(0, OFF, hour=15)]
    alerts = activation_timing(reads, alert_days=0)
    assert {a["kind"] for a in alerts} == {"late_activation", "early_deactivation"}
    assert next(a for a in alerts if a["kind"] == "late_activation")["days_late_at_least"] == 0


@pytest.mark.parametrize("basis", ["sell_out", None, "unknown"])
@pytest.mark.parametrize("statuses", [(OFF,), (AT, OFF)])
def test_non_promotion_evidence_cannot_raise_timing_alerts(basis, statuses):
    reads = [_obs(3 + i, status, basis=basis) for i, status in enumerate(statuses)]
    assert activation_timing(reads, alert_days=3) == []


def test_legacy_checks_without_a_price_basis_do_not_prove_promotion_timing():
    legacy = _obs(3, OFF)
    del legacy.parse_flags["cpor_activation"]["price_basis"]
    assert activation_timing([legacy], alert_days=3) == []


@pytest.mark.parametrize(
    "reads, expected",
    [
        ([_obs(0, AT, basis="sell_out"), _obs(3, OFF)], ["late_activation"]),
        ([_obs(0, AT), _obs(3, OFF, basis="sell_out")], []),
    ],
)
def test_fallback_checks_do_not_create_promotion_transitions(reads, expected):
    assert [a["kind"] for a in activation_timing(reads, alert_days=3)] == expected


def test_fallback_check_does_not_count_as_a_promotion_recovery():
    reads = [_obs(0, AT), _obs(3, OFF), _obs(3, AT, hour=15, basis="sell_out")]
    (early,) = activation_timing(reads, alert_days=3)
    assert early["kind"] == "early_deactivation"
    assert early["back_at_price_on"] is None


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
    monkeypatch.setenv("CIP_LISTING_ACTIVATION_ALERT_DAYS", "0")
    assert Settings(_env_file=None, **base).cip_listing_activation_alert_days == 0
    monkeypatch.setenv("CIP_LISTING_ACTIVATION_ALERT_DAYS", "-1")
    with pytest.raises(ValueError):
        Settings(_env_file=None, **base)
