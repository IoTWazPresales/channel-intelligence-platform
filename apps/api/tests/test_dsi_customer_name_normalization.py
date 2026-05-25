"""DSI customer name normalisation (no database)."""

from __future__ import annotations

from app.services.imports.dsi_customer_intelligence import annotate_dsi_customer_candidate_duplicates
from app.services.imports.dsi_customer_name_normalization import (
    dsi_duplicate_similarity_score,
    normalize_customer_name_for_similarity,
)


def test_normalize_strips_pty_ltd_and_whitespace() -> None:
    assert normalize_customer_name_for_similarity("  Acme Trading Pty Ltd.  ") == "acme trading"
    assert normalize_customer_name_for_similarity("Foo Bar t/a Baz Inc") == "foo bar baz"


def test_normalize_strips_cc_npc_and_ampersand() -> None:
    assert normalize_customer_name_for_similarity("Amoeba Trading CC") == "amoeba trading"
    assert normalize_customer_name_for_similarity("Acme NPC") == "acme"
    assert normalize_customer_name_for_similarity("B & A Computronics") == "b and a computronics"
    assert (
        normalize_customer_name_for_similarity("Amoeba Trading CC T/A Big Solutions")
        == normalize_customer_name_for_similarity("Amoeba Trading t/a Big Solutions")
    )


def test_normalize_trading_as_paren_mid_and_suffix() -> None:
    assert normalize_customer_name_for_similarity("Amoeba (t/a) Big Solutions") == "amoeba big solutions"
    assert normalize_customer_name_for_similarity("Ends with t/a") == "ends with"
    assert normalize_customer_name_for_similarity("Something trading-as Other") == "something other"


def test_amoeba_cc_and_ta_variants_duplicate_hint() -> None:
    assert dsi_duplicate_similarity_score("Amoeba Trading CC", "Amoeba Trading") is not None
    assert (
        dsi_duplicate_similarity_score(
            "Amoeba Trading CC T/A Big Solutions",
            "Amoeba Trading t/a Big Solutions",
        )
        is not None
    )


def test_ampersand_and_and_duplicate_hint() -> None:
    assert dsi_duplicate_similarity_score("B & A Computronics", "B and A Computronics") is not None


def test_acme_npc_duplicate_hint() -> None:
    assert dsi_duplicate_similarity_score("Acme NPC", "Acme") is not None


def test_cc_suffix_does_not_strip_inside_bcs_acronym() -> None:
    assert normalize_customer_name_for_similarity("BCS Computers cc") == "bcs computers"
    assert dsi_duplicate_similarity_score("BCS Computers", "RBS Computers") is None


def test_duplicate_annotation_within_job() -> None:
    dist_scope = {101}
    agg = {
        ("customer_dealer_token", "acme"): {
            "dealer_group_raw": "Acme Pty Ltd",
            "source_customer_raw_samples": [],
            "customer_evidence_norms": [],
            "sellout_distributor_ids": set(dist_scope),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "acme2"): {
            "dealer_group_raw": "ACME PTY LTD",
            "source_customer_raw_samples": [],
            "customer_evidence_norms": [],
            "sellout_distributor_ids": set(dist_scope),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    hints_a = agg[("customer_dealer_token", "acme")].get("possible_duplicate_of")
    assert isinstance(hints_a, list) and len(hints_a) >= 1
    assert hints_a[0]["normalized_key"] == "acme2"
    assert float(hints_a[0]["similarity_score"]) >= 0.88
    assert hints_a[0].get("match_basis") in ("dealer_group_exact", "dealer_group_similar")


def test_duplicate_annotation_skips_non_overlapping_distributors() -> None:
    agg = {
        ("customer_dealer_token", "acme"): {
            "dealer_group_raw": "Acme Pty Ltd",
            "source_customer_raw_samples": [],
            "customer_evidence_norms": [],
            "sellout_distributor_ids": {1},
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "acme2"): {
            "dealer_group_raw": "ACME PTY LTD",
            "source_customer_raw_samples": [],
            "customer_evidence_norms": [],
            "sellout_distributor_ids": {2},
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    assert not agg[("customer_dealer_token", "acme")].get("possible_duplicate_of")
