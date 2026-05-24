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


def test_ai_eq_systems_vs_ai_technology_not_duplicate() -> None:
    assert dsi_duplicate_similarity_score("AI EQ Systems", "AI Technology") is None


def test_ai_barakah_vs_ai_barak_duplicate() -> None:
    score = dsi_duplicate_similarity_score("AI Barakah", "AI Barak")
    assert score is not None
    assert score >= 0.88


def test_ai_barakah_multi_purpose_hyphen_duplicate() -> None:
    score = dsi_duplicate_similarity_score(
        "AI Barakah Multi Purpose",
        "AI Barakah Multi-Purpose",
    )
    assert score is not None
    assert score >= 0.88


def test_pc_world_vs_pc_direct_not_duplicate() -> None:
    assert dsi_duplicate_similarity_score("PC World", "PC Direct") is None


def test_hp_solutions_vs_hp_systems_not_duplicate() -> None:
    assert dsi_duplicate_similarity_score("HP Solutions", "HP Systems") is None


def test_acme_pty_ltd_vs_acme_technologies_duplicate() -> None:
    score = dsi_duplicate_similarity_score("Acme Pty Ltd", "Acme Technologies")
    assert score is not None
    assert score >= 0.88


def test_axiom_systems_vs_axiom_systems_africa_duplicate() -> None:
    score = dsi_duplicate_similarity_score("Axiom Systems", "Axiom Systems Africa")
    assert score is not None
    assert score >= 0.88


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
