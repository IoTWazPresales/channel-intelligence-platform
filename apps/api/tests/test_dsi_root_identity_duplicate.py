"""Root identity duplicate scorer — tests by category (written before implementation)."""

from __future__ import annotations

from app.services.imports.dsi_customer_intelligence import annotate_dsi_customer_candidate_duplicates
from app.services.imports.dsi_customer_name_normalization import (
    compare_root_identities,
    evaluate_company_stem_duplicate,
    evaluate_dealer_group_duplicate,
    extract_root_identity,
    extract_root_identity_from_raw,
    dsi_duplicate_similarity_score,
    normalize_customer_name_for_similarity,
)


# --- 1. Normalization invariants (roots use normalized input) ---


def test_normalize_legal_and_ta_still_apply_before_root() -> None:
    assert normalize_customer_name_for_similarity("Amoeba Trading CC") == "amoeba trading"
    assert normalize_customer_name_for_similarity("B & A Corp") == "b and a"


# --- 2. Root extraction ---


def test_extract_root_keeps_trading_in_registered_name() -> None:
    assert extract_root_identity_from_raw("Amoeba Trading CC") == "amoeba trading"
    assert extract_root_identity_from_raw("Amoeba Trading t/a Big Solutions") == "amoeba trading"


def test_extract_root_peels_service_product_tails() -> None:
    assert extract_root_identity_from_raw("Afrika Tikkun Services (Pty) Ltd") == "afrika tikkun"
    assert extract_root_identity_from_raw("Acme Technologies") == "acme"
    assert extract_root_identity_from_raw("Acme Solutions") == "acme"


def test_extract_root_peels_branch_style_tails() -> None:
    assert extract_root_identity_from_raw("Afrihost Home Connect (Pty) Ltd") == "afrihost"
    assert extract_root_identity_from_raw("Afrihost SP (Pty) Ltd") == "afrihost"


def test_extract_root_preserves_initials_and_short_tokens_in_identity() -> None:
    assert extract_root_identity_from_raw("B & A Computronics") == "b and a computronics"
    assert extract_root_identity_from_raw("B C S Computers") == "bcs"


def test_extract_root_strips_ta_alias_tail_words() -> None:
    norm = normalize_customer_name_for_similarity("Algoa Office Automantion t/a Nashua")
    assert "nashua" not in extract_root_identity(norm)
    assert extract_root_identity_from_raw("Algoa Office Automation") == "algoa office automation"


# --- 3. Must-match roots (business rule positives) ---


def test_must_match_afrihost_product_lines() -> None:
    ev = evaluate_dealer_group_duplicate(
        "Afrihost Home Connect (Pty) Ltd",
        "Afrihost SP (Pty) Ltd",
    )
    assert ev is not None
    assert ev.score >= 0.88


def test_must_match_afrika_tikkun_variants() -> None:
    ev = evaluate_dealer_group_duplicate("Afrika Tikkun NPC", "Afrika Tikkun Services (Pty) Ltd")
    assert ev is not None


def test_must_match_amoeba_trading_variants() -> None:
    assert evaluate_dealer_group_duplicate("Amoeba Trading CC", "Amoeba Trading") is not None
    assert (
        evaluate_dealer_group_duplicate(
            "Amoeba Trading CC T/A Big Solutions",
            "Amoeba Trading t/a Big Solutions",
        )
        is not None
    )


def test_must_match_algoa_typo_and_ta() -> None:
    ev = evaluate_dealer_group_duplicate(
        "Algoa Office Automantion t/a Nashua",
        "Algoa Office Automation",
    )
    assert ev is not None


def test_must_match_legal_suffix_and_ampersand_variants() -> None:
    assert evaluate_dealer_group_duplicate("Acme Pty Ltd", "ACME PTY LTD") is not None
    assert evaluate_dealer_group_duplicate("B & A Computronics", "B and A Computronics") is not None
    assert evaluate_dealer_group_duplicate("Acme NPC", "Acme") is not None


def test_must_match_acme_technology_line_variants() -> None:
    assert evaluate_dealer_group_duplicate("Acme Technologies", "Acme Solutions") is not None
    assert evaluate_dealer_group_duplicate("Acme Technology", "Acme Technologies") is not None


def test_must_match_adriane_ta_tail_via_root_not_prefix_stem() -> None:
    assert evaluate_company_stem_duplicate(
        "adriane investments (pty) ltd",
        "adriane investments (pty)ltd a/t klinsta",
    ) is None
    ev = evaluate_dealer_group_duplicate(
        "adriane investments (pty) ltd",
        "adriane investments (pty)ltd a/t klinsta",
    )
    assert ev is not None
    assert ev.match_basis in ("dealer_group_exact", "dealer_group_similar")


# --- 4. Must-not-match roots ---


def test_must_not_match_different_acronyms() -> None:
    assert evaluate_dealer_group_duplicate("BCS Computers", "RBS Computers") is None
    assert evaluate_dealer_group_duplicate("BCS Computers", "SBC Computers") is None
    assert evaluate_dealer_group_duplicate("TB Computers", "B4 Computers") is None
    assert evaluate_dealer_group_duplicate("FT Computers", "TB Computers") is None


def test_must_not_match_tb_computers_vs_tb_solutions() -> None:
    assert evaluate_dealer_group_duplicate("TB Computers", "TB Solutions") is None


def test_must_not_match_pc_world_vs_pc_direct() -> None:
    assert evaluate_dealer_group_duplicate("PC World", "PC Direct") is None


def test_must_not_match_unrelated_names_with_accidental_overlap() -> None:
    assert evaluate_dealer_group_duplicate(
        "C & B Information Technologies",
        "Computer Systems & Information",
    ) is None


def test_must_not_match_technology_cluster_different_distinctive_leads() -> None:
    assert evaluate_dealer_group_duplicate("Aeonic Technologies (Pty) Ltd", "benric technologies") is None
    assert evaluate_dealer_group_duplicate("Aeonic Technologies (Pty) Ltd", "omni technologies (pty) ltd") is None


def test_must_not_match_nrc_ngr_ocr_flip() -> None:
    assert evaluate_dealer_group_duplicate("NRC Computers cc", "ngr computers cc") is None


# --- 5. Short lead exact match ---


def test_short_lead_tb_vs_ta_no_match() -> None:
    assert compare_root_identities(extract_root_identity_from_raw("TB"), extract_root_identity_from_raw("TA")) is None


def test_short_lead_tb_exact_match() -> None:
    assert compare_root_identities(extract_root_identity_from_raw("TB"), extract_root_identity_from_raw("TB")) == 1.0


# --- 6. No partial overlap (prefix stem retired) ---


def test_prefix_only_extension_without_root_fuzzy_match_fails() -> None:
    assert compare_root_identities("alpha beta", "alpha beta gamma delta") is None


# --- 7. BCS positive edge cases ---


def test_bcs_computer_singular_plural_still_matches() -> None:
    ev = evaluate_dealer_group_duplicate("BCS Computers", "BCS Computer")
    assert ev is not None
    assert ev.score >= 0.88


def test_spaced_acronym_bcs_still_matches() -> None:
    ev = evaluate_dealer_group_duplicate("B C S Computers", "BCS Computers")
    assert ev is not None


# --- 8. Cloud it/its variant on roots ---


def test_cloud_it_its_still_matches() -> None:
    assert dsi_duplicate_similarity_score(
        "Cloud It Support Services (Pty) Ltd",
        "cloud its (pty) ltd",
    ) is not None


# --- 9. Annotate integration ---


def test_annotate_adriane_uses_dealer_group_root_not_prefix_stem() -> None:
    dist = {5}
    agg = {
        ("customer_dealer_token", "adriane investments (pty) ltd"): {
            "dealer_group_raw": "adriane investments (pty) ltd",
            "source_customer_raw_samples": ["adriane investments (pty) ltd"],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "adriane investments (pty)ltd a/t klinsta"): {
            "dealer_group_raw": "adriane investments (pty)ltd a/t klinsta",
            "source_customer_raw_samples": ["adriane investments (pty)ltd a/t klinsta"],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    hints = agg[("customer_dealer_token", "adriane investments (pty) ltd")].get("possible_duplicate_of")
    assert isinstance(hints, list) and len(hints) == 1
    assert hints[0]["match_basis"] in ("dealer_group_exact", "dealer_group_similar")
    assert hints[0]["match_basis"] != "dealer_group_prefix_stem"


def test_annotate_aeonic_cluster_still_no_false_positive() -> None:
    dist = {99}
    agg = {
        ("customer_dealer_token", "aeonic technologies (pty) ltd"): {
            "dealer_group_raw": "Aeonic Technologies (Pty) Ltd",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "benric technologies"): {
            "dealer_group_raw": "benric technologies",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "omni technologies (pty) ltd"): {
            "dealer_group_raw": "omni technologies (pty) ltd",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    assert not agg[("customer_dealer_token", "aeonic technologies (pty) ltd")].get("possible_duplicate_of")
