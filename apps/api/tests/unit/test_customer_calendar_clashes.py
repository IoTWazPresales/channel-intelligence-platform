"""Clash maths for the customer promotion calendar. Pure function, no database."""

from __future__ import annotations

from datetime import date

from app.services.cpor.customer_calendar.clashes import compute_clashes, overlap_days


def _promo(case_id: int, customer_id: int, start: date, end: date, **extra):
    return {
        "case_id": case_id,
        "case_code": f"CASE-{case_id}",
        "customer_id": customer_id,
        "window_start": start,
        "window_end": end,
        **extra,
    }


def _event(
    event_id: int,
    customer_id: int,
    start: date,
    end: date,
    name: str = "Event",
    kind: str = "campaign",
):
    return {
        "id": event_id,
        "customer_id": customer_id,
        "name": name,
        "kind": kind,
        "start_date": start,
        "end_date": end,
    }


def test_overlap_days_is_inclusive_and_zero_when_apart():
    assert overlap_days(
        date(2026, 3, 1), date(2026, 3, 10), date(2026, 3, 5), date(2026, 3, 20)
    ) == (
        date(2026, 3, 5),
        date(2026, 3, 10),
        6,
    )
    assert (
        overlap_days(date(2026, 3, 1), date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 20))
        is None
    )


def test_overlapping_window_is_a_clash_with_overlap_days_and_the_event():
    promos = [_promo(1, 7, date(2026, 3, 1), date(2026, 3, 15))]
    events = [
        _event(10, 7, date(2026, 3, 10), date(2026, 3, 31), name="Spring pillar", kind="pillar")
    ]
    out = compute_clashes(promos, events)
    assert len(out) == 1
    c = out[0]
    assert c["customer_id"] == 7
    assert c["case_id"] == 1
    assert c["event_id"] == 10
    assert c["overlap_start"] == date(2026, 3, 10)
    assert c["overlap_end"] == date(2026, 3, 15)
    assert c["overlap_days"] == 6
    assert c["event"]["name"] == "Spring pillar"
    assert c["event"]["kind"] == "pillar"
    assert c["promotion"]["case_code"] == "CASE-1"


def test_same_day_touch_counts_as_one_day_overlap():
    promos = [_promo(1, 7, date(2026, 3, 1), date(2026, 3, 10))]
    events = [_event(10, 7, date(2026, 3, 10), date(2026, 3, 12))]
    out = compute_clashes(promos, events)
    assert [c["overlap_days"] for c in out] == [1]


def test_adjacent_days_are_not_a_clash():
    promos = [_promo(1, 7, date(2026, 3, 1), date(2026, 3, 10))]
    events = [_event(10, 7, date(2026, 3, 11), date(2026, 3, 12))]
    assert compute_clashes(promos, events) == []


def test_other_customer_never_clashes():
    promos = [_promo(1, 7, date(2026, 3, 1), date(2026, 3, 10))]
    events = [_event(10, 8, date(2026, 3, 1), date(2026, 3, 10))]
    assert compute_clashes(promos, events) == []


def test_event_inside_window_and_window_inside_event():
    promos = [
        _promo(1, 7, date(2026, 3, 1), date(2026, 3, 31)),
        _promo(2, 7, date(2026, 5, 10), date(2026, 5, 12)),
    ]
    events = [
        _event(10, 7, date(2026, 3, 10), date(2026, 3, 12)),
        _event(11, 7, date(2026, 5, 1), date(2026, 5, 31)),
    ]
    out = compute_clashes(promos, events)
    assert [(c["case_id"], c["event_id"], c["overlap_days"]) for c in out] == [
        (1, 10, 3),
        (2, 11, 3),
    ]


def test_one_window_against_two_events_gives_two_clashes_in_stable_order():
    promos = [_promo(1, 7, date(2026, 3, 1), date(2026, 3, 31))]
    events = [
        _event(12, 7, date(2026, 3, 20), date(2026, 3, 25)),
        _event(11, 7, date(2026, 3, 5), date(2026, 3, 9)),
    ]
    out = compute_clashes(promos, events)
    assert [c["event_id"] for c in out] == [11, 12]


def test_events_without_a_customer_are_ignored():
    promos = [_promo(1, 7, date(2026, 3, 1), date(2026, 3, 31))]
    events = [_event(10, None, date(2026, 3, 1), date(2026, 3, 31))]
    assert compute_clashes(promos, events) == []


def test_iso_strings_are_accepted_for_dates():
    promos = [_promo(1, 7, "2026-03-01", "2026-03-10")]
    events = [_event(10, 7, "2026-03-05", "2026-03-06")]
    out = compute_clashes(promos, events)
    assert out[0]["overlap_days"] == 2
    assert out[0]["overlap_start"] == date(2026, 3, 5)


def test_empty_inputs():
    assert compute_clashes([], []) == []
    assert compute_clashes([_promo(1, 7, date(2026, 3, 1), date(2026, 3, 2))], []) == []
