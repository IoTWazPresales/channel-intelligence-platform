"""Unit tests for distributor receipt disambiguation tiers (no database)."""

from __future__ import annotations

from datetime import date

from app.services.imports.dsi_distributor_receipt_disambiguation import (
    DistributorReceiptProductIndex,
    _pick_by_transition_date,
    _windows_strictly_separated,
    try_receipt_disambiguate_product,
)


def test_t1_single_receipt_intersection() -> None:
    idx = DistributorReceiptProductIndex()
    idx._dist[("mustek", "fa506ncr-716512b0w")][13164] = [date(2025, 1, 14)]
    idx._line_counts[("mustek", "fa506ncr-716512b0w")] = 1
    res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="FA506NCR-716512B0W",
        eligible_product_ids=[12862, 13164],
        evidence_date=date(2025, 3, 1),
        ambiguous_eligible={"product_ids": [12862, 13164], "tier": "sales_model_name"},
    )
    assert res.tier == "T1"
    assert res.product_id == 13164


def test_t2_transition_picks_older_sku_before_first_ship_of_new() -> None:
    pid_dates = {
        12862: [date(2024, 8, 1)],
        13164: [date(2025, 1, 14)],
    }
    assert _windows_strictly_separated(pid_dates)
    pick_old = _pick_by_transition_date({12862, 13164}, pid_dates, date(2024, 9, 1))
    pick_new = _pick_by_transition_date({12862, 13164}, pid_dates, date(2025, 2, 1))
    assert pick_old == 12862
    assert pick_new == 13164


def test_overlapping_windows_fail_t2() -> None:
    pid_dates = {
        12862: [date(2024, 8, 1), date(2025, 2, 1)],
        13164: [date(2025, 1, 14)],
    }
    assert not _windows_strictly_separated(pid_dates)
