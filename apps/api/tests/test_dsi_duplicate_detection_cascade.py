"""DSI duplicate detection cascade (distinctive stem gate + full-string check)."""

from __future__ import annotations

from app.services.imports.dsi_customer_intelligence import annotate_dsi_customer_candidate_duplicates
from app.services.imports.dsi_customer_name_normalization import (
    dsi_duplicate_similarity_score,
    split_distinctive_and_generic_tokens,
)


def test_split_distinctive_and_generic() -> None:
    dist, gen = split_distinctive_and_generic_tokens("aeonic technologies")
    assert dist == "aeonic"
    assert gen == "technologies"
    dist_bcs, gen_bcs = split_distinctive_and_generic_tokens("bcs computers")
    assert dist_bcs == "bcs"
    assert gen_bcs == "computers"


def test_bcs_vs_rbs_no_dealer_group_similarity() -> None:
    assert dsi_duplicate_similarity_score("BCS Computers", "RBS Computers") is None


def test_bcs_vs_sbc_no_dealer_group_similarity() -> None:
    assert dsi_duplicate_similarity_score("BCS Computers", "SBC Computers") is None


def test_bcs_vs_rbs_prior_branch_was_full_string_on_shared_tail() -> None:
    """Regression: before generic ``computers`` + short-lead gate, score was ~0.9231 via full_ratio."""
    from difflib import SequenceMatcher

    from app.services.imports.dsi_customer_name_normalization import (
        _normalize_for_duplicate_compare,
        split_distinctive_and_generic_tokens,
    )

    na = _normalize_for_duplicate_compare("BCS Computers")
    nb = _normalize_for_duplicate_compare("RBS Computers")
    da, _ = split_distinctive_and_generic_tokens(na)
    db, _ = split_distinctive_and_generic_tokens(nb)
    assert da == "bcs" and db == "rbs"
    assert SequenceMatcher(None, na, nb).ratio() >= 0.88
    assert dsi_duplicate_similarity_score("BCS Computers", "RBS Computers") is None


def test_bcs_computers_vs_bcs_computer_still_hints() -> None:
    score = dsi_duplicate_similarity_score("BCS Computers", "BCS Computer")
    assert score is not None
    assert score >= 0.88


def test_spaced_acronym_bcs_vs_bcs_still_hints() -> None:
    score = dsi_duplicate_similarity_score("B C S Computers", "BCS Computers")
    assert score is not None
    assert score >= 0.88


def test_aeonic_benric_omni_not_duplicates() -> None:
    assert dsi_duplicate_similarity_score("Aeonic Technologies (Pty) Ltd", "benric technologies") is None
    assert dsi_duplicate_similarity_score("Aeonic Technologies (Pty) Ltd", "omni technologies (pty) ltd") is None
    assert dsi_duplicate_similarity_score("benric technologies", "omni technologies (pty) ltd") is None


def test_acme_legal_variants_duplicate() -> None:
    score = dsi_duplicate_similarity_score("Acme Pty Ltd", "ACME PTY LTD")
    assert score is not None
    assert score >= 0.88


def test_acme_technologies_vs_solutions_same_stem() -> None:
    score = dsi_duplicate_similarity_score("Acme Technologies", "Acme Solutions")
    assert score is not None


def test_acme_technology_vs_technologies_same_stem() -> None:
    score = dsi_duplicate_similarity_score("Acme Technology", "Acme Technologies")
    assert score is not None


def test_annotate_job_rejects_aeonic_cluster_false_positives() -> None:
    dist = {99}
    agg = {
        ("customer_dealer_token", "aeonic technologies (pty) ltd"): {
            "dealer_group_raw": "Aeonic Technologies (Pty) Ltd",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": set(dist),
            "row_count": 2,
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


def test_nrc_ngr_not_duplicate() -> None:
    assert dsi_duplicate_similarity_score("NRC Computers cc", "ngr computers cc") is None


def test_cloud_it_vs_cloud_its_still_duplicate() -> None:
    score = dsi_duplicate_similarity_score(
        "Cloud It Support Services (Pty) Ltd",
        "cloud its (pty) ltd",
    )
    assert score is not None
    assert score >= 0.88


def test_tb_vs_b4_computers_not_duplicate() -> None:
    assert dsi_duplicate_similarity_score("TB Computers", "B4 Computers") is None


def test_ft_vs_tb_computers_not_duplicate() -> None:
    assert dsi_duplicate_similarity_score("FT Computers", "TB Computers") is None


def test_tb_computers_vs_tb_solutions_no_short_stem_dealer_hint() -> None:
    """Unsafe prior behaviour: same 2-char stem ``tb`` forced a dealer-group hint."""
    assert dsi_duplicate_similarity_score("TB Computers", "TB Solutions") is None


def test_pc_world_vs_pc_direct_no_short_stem_dealer_hint() -> None:
    assert dsi_duplicate_similarity_score("PC World", "PC Direct") is None


def test_adriane_root_duplicate_not_prefix_stem() -> None:
    from app.services.imports.dsi_customer_name_normalization import evaluate_dealer_group_duplicate

    ev = evaluate_dealer_group_duplicate(
        "adriane investments (pty) ltd",
        "adriane investments (pty)ltd a/t klinsta",
    )
    assert ev is not None
    assert ev.match_basis in ("dealer_group_exact", "dealer_group_similar")


def test_annotate_adriane_pair_gets_root_hint() -> None:
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


def test_annotate_shared_dealer_group_different_source_gets_shared_label_hint() -> None:
    dist = {1}
    dg = "Afrihost (Pty) Ltd"
    agg = {
        ("customer_dealer_token", "afrihost branch a"): {
            "dealer_group_raw": dg,
            "source_customer_raw_samples": ["Afrihost Branch A"],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "afrihost branch b"): {
            "dealer_group_raw": dg,
            "source_customer_raw_samples": ["Afrihost Branch B"],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    hints = agg[("customer_dealer_token", "afrihost branch a")].get("possible_duplicate_of")
    assert isinstance(hints, list) and len(hints) == 1
    assert hints[0]["match_basis"] == "dealer_group_shared_label_different_counterparty"


def test_annotate_job_keeps_true_acme_duplicates() -> None:
    dist = {1}
    agg = {
        ("customer_dealer_token", "acme"): {
            "dealer_group_raw": "Acme Pty Ltd",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
        ("customer_dealer_token", "acme2"): {
            "dealer_group_raw": "ACME PTY LTD",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": set(dist),
            "row_count": 1,
            "total_units": 0,
            "total_value": 0,
            "samples": [],
        },
    }
    annotate_dsi_customer_candidate_duplicates(agg)
    hints = agg[("customer_dealer_token", "acme")].get("possible_duplicate_of")
    assert isinstance(hints, list) and len(hints) == 1
    assert hints[0]["normalized_key"] == "acme2"
    assert hints[0].get("match_basis") in ("dealer_group_exact", "dealer_group_similar")
