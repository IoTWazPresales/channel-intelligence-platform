"""Phase A.5 — duplicate hint contract (parse/types only; no DB)."""

from __future__ import annotations

from app.services.imports.dsi_duplicate_hint_contract import (
    MATCH_BASIS_ACTIVE,
    MATCH_BASIS_CROSS_DISTI,
    MATCH_BASIS_DEALER_GROUP_PREFIX_STEM,
    MATCH_BASIS_DEALER_GROUP_SHARED_LABEL,
    MATCH_BASIS_RESERVED,
    MATCH_BASIS_SOURCE_CUSTOMER_EXACT,
    MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR,
    MATCH_BASIS_TEMPORAL_SAME_DISTI,
    build_duplicate_hint_entry,
    is_known_match_basis,
    is_reserved_match_basis,
    parse_duplicate_hint_entry,
)


def test_active_match_bases_are_known_not_reserved() -> None:
    for basis in MATCH_BASIS_ACTIVE:
        assert is_known_match_basis(basis)
        assert not is_reserved_match_basis(basis)
    assert MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR in MATCH_BASIS_ACTIVE
    assert MATCH_BASIS_DEALER_GROUP_PREFIX_STEM in MATCH_BASIS_ACTIVE
    assert MATCH_BASIS_DEALER_GROUP_SHARED_LABEL in MATCH_BASIS_ACTIVE


def test_reserved_match_bases_parse_without_loss() -> None:
    for basis in MATCH_BASIS_RESERVED:
        assert is_reserved_match_basis(basis)
        assert is_known_match_basis(basis)
        raw = {
            "normalized_key": "peer token",
            "similarity_score": 0.92,
            "match_basis": basis,
        }
        parsed = parse_duplicate_hint_entry(raw)
        assert parsed is not None
        assert parsed["match_basis"] == basis


def test_build_minimal_hint_backwards_compatible() -> None:
    entry = build_duplicate_hint_entry(
        normalized_key="acme retail",
        similarity_score=0.91,
        match_basis=MATCH_BASIS_SOURCE_CUSTOMER_EXACT,
    )
    assert entry == {
        "normalized_key": "acme retail",
        "similarity_score": 0.91,
        "match_basis": MATCH_BASIS_SOURCE_CUSTOMER_EXACT,
    }


def test_build_and_parse_optional_evidence_metadata() -> None:
    entry = build_duplicate_hint_entry(
        normalized_key="peer",
        similarity_score=1.0,
        match_basis=MATCH_BASIS_TEMPORAL_SAME_DISTI,
        matched_value="acme ltd",
        matched_field="dealer_group_raw",
        dealer_group_norm="acme",
        source_customer_norm="acme store 1",
        distributor_scope=[3, 7],
        evidence_reason="same_disti_transaction_overlap",
    )
    parsed = parse_duplicate_hint_entry(entry)
    assert parsed is not None
    assert parsed["matched_value"] == "acme ltd"
    assert parsed["matched_field"] == "dealer_group_raw"
    assert parsed["dealer_group_norm"] == "acme"
    assert parsed["source_customer_norm"] == "acme store 1"
    assert parsed["distributor_scope"] == [3, 7]
    assert parsed["evidence_reason"] == "same_disti_transaction_overlap"
    assert parsed["match_basis"] == MATCH_BASIS_TEMPORAL_SAME_DISTI


def test_parse_legacy_string_hint() -> None:
    assert parse_duplicate_hint_entry("legacy key") == {"normalized_key": "legacy key"}


def test_parse_unknown_match_basis_preserved() -> None:
    raw = {"normalized_key": "x", "match_basis": "future_basis_v2"}
    parsed = parse_duplicate_hint_entry(raw)
    assert parsed is not None
    assert parsed["match_basis"] == "future_basis_v2"


def test_annotate_does_not_emit_reserved_match_bases() -> None:
    """Reserved bases exist for forward compatibility only — not written by Phase A annotate."""
    import inspect

    from app.services.imports import dsi_customer_intelligence as intel

    source = inspect.getsource(intel.annotate_dsi_customer_candidate_duplicates)
    for reserved in (MATCH_BASIS_TEMPORAL_SAME_DISTI, MATCH_BASIS_CROSS_DISTI):
        assert reserved not in source, f"annotate must not emit {reserved!r} yet"
    assert MATCH_BASIS_CROSS_DISTI in MATCH_BASIS_RESERVED
