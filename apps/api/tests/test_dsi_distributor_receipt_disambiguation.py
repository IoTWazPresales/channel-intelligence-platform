"""Unit tests for per-distributor receipt disambiguation (final tier, no database)."""

from __future__ import annotations

from datetime import date

from app.services.imports.dsi_distributor_receipt_disambiguation import (
    REASON_OVERLAP_REFINED,
    REASON_SINGLE,
    STATUS_AMBIGUOUS_OVERLAP,
    STATUS_NO_RECEIPT_EVIDENCE,
    STATUS_RESOLVED_SINGLE,
    DistributorReceiptProductIndex,
    ReceiptLineEvidence,
    _refine_overlap_candidates,
    _window_covers_tx,
    try_receipt_disambiguate_product,
)


def _idx_with_lines(
    canon: str,
    sm: str,
    lines: list[ReceiptLineEvidence],
) -> DistributorReceiptProductIndex:
    idx = DistributorReceiptProductIndex()
    for ln in lines:
        idx._dist[(canon, sm)][int(ln.product_id)].append(ln)
        idx._line_counts[(canon, sm)] += 1
    return idx


def test_single_receipt_intersection_resolves_distributor_receipt_single() -> None:
    idx = _idx_with_lines(
        "mustek",
        "fa506ncr-716512b0w",
        [ReceiptLineEvidence(13164, date(2025, 1, 14), date(2025, 2, 1), 50.0)],
    )
    res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="FA506NCR-716512B0W",
        eligible_product_ids=[12862, 13164],
        evidence_date=date(2025, 3, 1),
        ambiguous_eligible={"product_ids": [12862, 13164], "tier": "sales_model_name"},
        sell_out_qty=2.0,
    )
    assert res.resolve_reason == REASON_SINGLE
    assert res.product_id == 13164
    assert res.evidence is not None
    assert res.evidence["status"] == STATUS_RESOLVED_SINGLE
    assert res.evidence["resolve_reason"] == REASON_SINGLE


def test_no_receipt_evidence_stays_reviewable_with_marker() -> None:
    idx = DistributorReceiptProductIndex()
    res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="UNKNOWN-MODEL",
        eligible_product_ids=[10, 20],
        evidence_date=date(2025, 3, 1),
        ambiguous_eligible={"product_ids": [10, 20], "tier": "sales_model_name"},
    )
    assert res.product_id is None
    assert res.resolve_reason is None
    assert res.evidence is not None
    assert res.evidence["status"] == STATUS_NO_RECEIPT_EVIDENCE


def test_overlap_refine_resolves_when_window_and_qty_unique() -> None:
    pid_lines = {
        12862: [ReceiptLineEvidence(12862, date(2024, 8, 1), date(2024, 12, 31), 100.0)],
        13164: [ReceiptLineEvidence(13164, date(2025, 1, 14), date(2025, 6, 30), 80.0)],
    }
    refined = _refine_overlap_candidates(
        {12862, 13164},
        pid_lines,
        evidence_date=date(2024, 9, 1),
        sell_out_qty=5.0,
    )
    assert refined == {12862}

    idx = _idx_with_lines(
        "mustek",
        "fa506ncr-716512b0w",
        pid_lines[12862] + pid_lines[13164],
    )
    res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="FA506NCR-716512B0W",
        eligible_product_ids=[12862, 13164],
        evidence_date=date(2024, 9, 1),
        ambiguous_eligible={"product_ids": [12862, 13164], "tier": "sales_model_name"},
        sell_out_qty=5.0,
    )
    assert res.resolve_reason == REASON_OVERLAP_REFINED
    assert res.product_id == 12862


def test_overlap_stays_ambiguous_with_receipt_evidence_attached() -> None:
    pid_lines = {
        12862: [ReceiptLineEvidence(12862, date(2024, 8, 1), date(2025, 6, 30), 100.0)],
        13164: [ReceiptLineEvidence(13164, date(2024, 9, 1), date(2025, 6, 30), 80.0)],
    }
    idx = _idx_with_lines(
        "mustek",
        "fa506ncr-716512b0w",
        pid_lines[12862] + pid_lines[13164],
    )
    res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="FA506NCR-716512B0W",
        eligible_product_ids=[12862, 13164],
        evidence_date=date(2024, 10, 1),
        ambiguous_eligible={"product_ids": [12862, 13164], "tier": "sales_model_name"},
        sell_out_qty=5.0,
    )
    assert res.product_id is None
    assert res.evidence is not None
    assert res.evidence["status"] == STATUS_AMBIGUOUS_OVERLAP
    assert len(res.evidence.get("receipt_lines") or []) >= 2


def test_two_feasible_skus_both_pass_window_and_qty_stay_ambiguous_not_qty_ranked() -> None:
    """Qty is a feasibility filter only — never pick the higher-shipped SKU when both survive."""
    pid_lines = {
        12862: [ReceiptLineEvidence(12862, date(2024, 8, 1), date(2025, 12, 31), 10.0)],
        13164: [ReceiptLineEvidence(13164, date(2024, 8, 1), date(2025, 12, 31), 500.0)],
    }
    refined = _refine_overlap_candidates(
        {12862, 13164},
        pid_lines,
        evidence_date=date(2024, 10, 1),
        sell_out_qty=5.0,
    )
    assert refined == {12862, 13164}

    idx = _idx_with_lines(
        "mustek",
        "fa506ncr-716512b0w",
        pid_lines[12862] + pid_lines[13164],
    )
    res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="FA506NCR-716512B0W",
        eligible_product_ids=[12862, 13164],
        evidence_date=date(2024, 10, 1),
        ambiguous_eligible={"product_ids": [12862, 13164], "tier": "sales_model_name"},
        sell_out_qty=5.0,
    )
    assert res.product_id is None
    assert res.resolve_reason is None
    assert res.evidence is not None
    assert res.evidence["status"] == STATUS_AMBIGUOUS_OVERLAP
    assert set(res.evidence.get("overlap_refine_survivors") or []) == {12862, 13164}
    assert len(res.evidence.get("receipt_lines") or []) >= 2


def test_single_sku_pick_is_deterministic_across_calls() -> None:
    idx = _idx_with_lines(
        "mustek",
        "fa506ncr-716512b0w",
        [ReceiptLineEvidence(13164, date(2025, 1, 14), date(2025, 2, 1), 50.0)],
    )
    kwargs = dict(
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="FA506NCR-716512B0W",
        eligible_product_ids=[12862, 13164],
        evidence_date=date(2025, 3, 1),
        ambiguous_eligible={"product_ids": [12862, 13164], "tier": "sales_model_name"},
        sell_out_qty=2.0,
    )
    picks = [
        try_receipt_disambiguate_product(idx, **kwargs).product_id for _ in range(5)
    ]
    assert picks == [13164, 13164, 13164, 13164, 13164]


def test_window_covers_tx_respects_pod() -> None:
    assert _window_covers_tx(date(2024, 8, 1), date(2024, 12, 31), date(2024, 10, 1))
    assert not _window_covers_tx(date(2024, 8, 1), date(2024, 9, 30), date(2024, 10, 1))


def test_qty_one_sample_line_does_not_pollute_receipt_t1_intersection() -> None:
    """Only qty>1 shipped lines belong in the receipt bucket (sample/demo units excluded)."""
    idx = _idx_with_lines(
        "mustek",
        "b3402fba-i71610b2x",
        [
            ReceiptLineEvidence(4080, date(2024, 3, 1), date(2024, 6, 30), 120.0),
            # qty=1 sample — must not appear in index built from strict load filters
        ],
    )
    # Simulate pollution: a second pid present only via qty=1 would have been in loose index
    polluted = _idx_with_lines(
        "mustek",
        "b3402fba-i71610b2x",
        [
            ReceiptLineEvidence(4080, date(2024, 3, 1), date(2024, 6, 30), 120.0),
            ReceiptLineEvidence(8858, date(2024, 3, 1), date(2024, 6, 30), 1.0),
        ],
    )
    clean_res = try_receipt_disambiguate_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="B3402FBA-I71610B2X",
        eligible_product_ids=[4080, 8858],
        evidence_date=date(2024, 4, 1),
        ambiguous_eligible={"product_ids": [4080, 8858], "tier": "sales_model_name"},
    )
    polluted_res = try_receipt_disambiguate_product(
        polluted,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        raw_product_token="B3402FBA-I71610B2X",
        eligible_product_ids=[4080, 8858],
        evidence_date=date(2024, 4, 1),
        ambiguous_eligible={"product_ids": [4080, 8858], "tier": "sales_model_name"},
    )
    assert clean_res.resolve_reason == REASON_SINGLE
    assert clean_res.product_id == 4080
    assert polluted_res.product_id is None
    assert polluted_res.evidence is not None
    assert polluted_res.evidence["status"] == STATUS_AMBIGUOUS_OVERLAP
