"""Unit tests for D-0119 distributor stock carry-forward (no DB)."""

from __future__ import annotations

from datetime import date

from app.query.model.stock_carry_forward import (
    StockObservation,
    carry_forward_all,
    carry_forward_pair_series,
    iter_bucket_starts,
    rollup_carry_rows,
)


def test_iter_month_buckets_cover_the_window():
    assert iter_bucket_starts(date(2026, 1, 15), date(2026, 3, 10), "month") == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]


def test_gap_period_carries_last_count_and_is_flagged():
    obs = [
        StockObservation(1, 10, date(2026, 1, 20), 40.0),
        StockObservation(1, 10, date(2026, 3, 5), 25.0),
    ]
    rows = carry_forward_pair_series(
        obs,
        buckets=[date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
        grain="month",
    )
    by = {r["bucket_start"]: r for r in rows}
    assert by[date(2026, 1, 1)]["on_hand"] == 40.0
    assert by[date(2026, 1, 1)]["carried_forward"] is False
    assert by[date(2026, 2, 1)]["on_hand"] == 40.0
    assert by[date(2026, 2, 1)]["carried_forward"] is True
    assert by[date(2026, 3, 1)]["on_hand"] == 25.0
    assert by[date(2026, 3, 1)]["carried_forward"] is False


def test_new_count_replaces_carried_value():
    obs = [
        StockObservation(1, 10, date(2026, 1, 10), 10.0),
        StockObservation(1, 10, date(2026, 2, 12), 7.0),
    ]
    rows = carry_forward_pair_series(
        obs,
        buckets=[date(2026, 1, 1), date(2026, 2, 1)],
        grain="month",
    )
    assert rows[1]["on_hand"] == 7.0 and rows[1]["carried_forward"] is False


def test_never_counted_pair_stays_empty():
    rows = carry_forward_all(
        [],
        period_from=date(2026, 1, 1),
        period_to=date(2026, 3, 31),
        grain="month",
    )
    assert rows == []


def test_buckets_before_first_count_are_omitted():
    obs = [StockObservation(1, 10, date(2026, 3, 1), 5.0)]
    rows = carry_forward_pair_series(
        obs,
        buckets=[date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
        grain="month",
    )
    assert [r["bucket_start"] for r in rows] == [date(2026, 3, 1)]
    assert rows[0]["carried_forward"] is False


def test_rollup_sums_products_and_flags_only_when_all_carried():
    pair_rows = [
        {
            "distributor_id": 1,
            "product_id": 10,
            "bucket_start": date(2026, 2, 1),
            "bucket_end": date(2026, 2, 28),
            "bucket_key": "2026-02",
            "on_hand": 40.0,
            "carried_forward": True,
        },
        {
            "distributor_id": 1,
            "product_id": 11,
            "bucket_start": date(2026, 2, 1),
            "bucket_end": date(2026, 2, 28),
            "bucket_key": "2026-02",
            "on_hand": 10.0,
            "carried_forward": False,
        },
    ]
    rolled = rollup_carry_rows(pair_rows, breakdowns=["period", "distributor"])
    assert len(rolled) == 1
    assert rolled[0]["on_hand"] == 50.0
    assert rolled[0]["carried_forward"] is False
    assert rolled[0]["distributor_id"] == 1


def test_same_date_rows_are_summed_before_carry():
    obs = [
        StockObservation(1, 10, date(2026, 1, 15), 3.0),
        StockObservation(1, 10, date(2026, 1, 15), 7.0),
    ]
    rows = carry_forward_pair_series(obs, buckets=[date(2026, 1, 1)], grain="month")
    assert len(rows) == 1
    assert rows[0]["on_hand"] == 10.0
    assert rows[0]["carried_forward"] is False

