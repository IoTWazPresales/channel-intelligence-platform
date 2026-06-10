"""Unit tests for dsi_product_shipment_tiebreak (removable component)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.services.imports.dsi_product_shipment_tiebreak import (
    build_tiebreak_scope_attempts,
    intersect_eligible_with_shipment_ids,
    parse_candidate_shipment_evidence,
    try_shipment_tiebreak_product_id,
)
from app.services.imports.dsi_shipment_corroboration import GlobalProductIdentityIndex


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


def test_build_tiebreak_scope_attempts_merges_staging() -> None:
    ctx = {
        "unresolved_distributor_ids": [38],
        "dsi_evidence_month_counts": {"2025-06": 10, "2025-07": 2},
    }
    staging = {"fa506nf-58512b0w": [(29, "2025-08")]}
    attempts = build_tiebreak_scope_attempts(
        ctx,
        normalized_key="fa506nf-58512b0w",
        staging_scopes=staging,
    )
    assert (38, date(2025, 6, 1)) in attempts
    assert (29, date(2025, 8, 1)) in attempts


def test_try_shipment_tiebreak_multi_scope_unanimous(monkeypatch) -> None:
    calls: list[tuple[int, date]] = []

    def fake_disambiguate(_db, dist_id, ev_date, _raw, _elig, corr_cache=None):
        calls.append((dist_id, ev_date))
        if dist_id == 38:
            return 101, "distributor_specific"
        return None, None

    monkeypatch.setattr(
        "app.services.imports.distributor_sales_inventory._shipment_disambiguate_product_id",
        fake_disambiguate,
    )
    pick, src = try_shipment_tiebreak_product_id(
        MagicMock(),
        eligible_product_ids=[101, 202],
        raw_token="TOKEN",
        distributor_id=None,
        evidence_date=None,
        candidate_context={
            "unresolved_distributor_ids": [38, 29],
            "dominant_evidence_month": "2025-06",
        },
        staging_scopes={"token": [(38, "2025-06")]},
        normalized_key="token",
    )
    assert pick == 101
    assert src == "shipment_disambiguate_multi_scope"
    assert calls


def test_try_shipment_tiebreak_multi_scope_conflict_returns_none(monkeypatch) -> None:
    def fake_disambiguate(_db, dist_id, _ev_date, _raw, _elig, corr_cache=None):
        return dist_id * 10, "distributor_specific"

    monkeypatch.setattr(
        "app.services.imports.distributor_sales_inventory._shipment_disambiguate_product_id",
        fake_disambiguate,
    )
    pick, src = try_shipment_tiebreak_product_id(
        MagicMock(),
        eligible_product_ids=[100, 200],
        raw_token="TOKEN",
        distributor_id=None,
        evidence_date=None,
        candidate_context={
            "unresolved_distributor_ids": [38, 29],
            "dominant_evidence_month": "2025-06",
        },
    )
    assert pick is None
    assert src is None


def _global_index(mapping: dict[str, tuple[int, ...]]) -> GlobalProductIdentityIndex:
    return GlobalProductIdentityIndex(mapping)


def test_try_shipment_tiebreak_global_singleton_in_eligible() -> None:
    idx = _global_index({"fa506nf-58512b0w": (42, 99)})
    pick, src = try_shipment_tiebreak_product_id(
        None,
        eligible_product_ids=[10, 42],
        raw_token="FA506NF-58512B0W",
        distributor_id=None,
        evidence_date=None,
        global_product_identity=idx,
    )
    assert pick == 42
    assert src == "shipment_global_identity"


def test_try_shipment_tiebreak_global_singleton_not_in_eligible() -> None:
    idx = _global_index({"fa506nf-58512b0w": (99,)})
    pick, src = try_shipment_tiebreak_product_id(
        None,
        eligible_product_ids=[10, 42],
        raw_token="fa506nf-58512b0w",
        distributor_id=None,
        evidence_date=None,
        global_product_identity=idx,
    )
    assert pick is None
    assert src is None


def test_try_shipment_tiebreak_global_intersection_of_two_returns_none() -> None:
    idx = _global_index({"token-x": (10, 20)})
    pick, src = try_shipment_tiebreak_product_id(
        None,
        eligible_product_ids=[10, 20],
        raw_token="token-x",
        distributor_id=None,
        evidence_date=None,
        global_product_identity=idx,
    )
    assert pick is None
    assert src is None


def test_try_shipment_tiebreak_global_token_absent() -> None:
    idx = _global_index({"other-token": (10,)})
    pick, src = try_shipment_tiebreak_product_id(
        None,
        eligible_product_ids=[10, 20],
        raw_token="missing-token",
        distributor_id=None,
        evidence_date=None,
        global_product_identity=idx,
    )
    assert pick is None
    assert src is None


def test_try_shipment_tiebreak_stored_context_wins_over_global(monkeypatch) -> None:
    idx = _global_index({"fa506": (99,)})
    monkeypatch.setattr(
        "app.services.imports.distributor_sales_inventory._shipment_disambiguate_product_id",
        lambda *_a, **_k: (99, "distributor_specific"),
    )
    pick, src = try_shipment_tiebreak_product_id(
        MagicMock(),
        eligible_product_ids=[10, 20],
        raw_token="FA506",
        distributor_id=5,
        evidence_date=date(2025, 6, 1),
        stored_distinct_product_ids=(20,),
        global_product_identity=idx,
        candidate_context={"dominant_evidence_month": "2025-06"},
    )
    assert pick == 20
    assert src == "stored_context"
