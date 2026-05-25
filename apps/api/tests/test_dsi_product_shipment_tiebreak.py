"""Unit tests for dsi_product_shipment_tiebreak (removable component)."""

from __future__ import annotations

from app.services.imports.dsi_product_shipment_tiebreak import (
    intersect_eligible_with_shipment_ids,
    parse_candidate_shipment_evidence,
    try_shipment_tiebreak_product_id,
)


def test_intersect_single_id() -> None:
    assert intersect_eligible_with_shipment_ids([10, 20], [20, 99]) == 20


def test_intersect_empty_or_ambiguous() -> None:
    assert intersect_eligible_with_shipment_ids([10, 20], [10, 20]) is None
    assert intersect_eligible_with_shipment_ids([10], []) is None


def test_parse_candidate_shipment_evidence() -> None:
    ctx = {
        "dominant_evidence_month": "2024-03",
        "dominant_unresolved_distributor_id": 5,
        "shipment_distinct_product_ids": [101, 102],
    }
    ev = parse_candidate_shipment_evidence(ctx)
    assert ev.dominant_evidence_month == "2024-03"
    assert ev.dominant_unresolved_distributor_id == 5
    assert ev.stored_distinct_product_ids == (101, 102)


def test_try_shipment_tiebreak_uses_stored_context() -> None:
    pick, src = try_shipment_tiebreak_product_id(
        None,
        eligible_product_ids=[10, 20],
        raw_token="FA506",
        distributor_id=5,
        evidence_date=None,
        stored_distinct_product_ids=(20,),
    )
    assert pick == 20
    assert src == "stored_context"
