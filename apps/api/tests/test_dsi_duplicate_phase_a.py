"""Phase A DSI duplicate hints: short-stem guard, source customer channel, match_basis."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_customer_intelligence import (
    annotate_dsi_customer_candidate_duplicates,
    dsi_candidate_duplicate_review_unresolved,
    gate_dsi_plan_row_duplicate_review,
)
from app.services.imports.dsi_customer_name_normalization import (
    dsi_duplicate_similarity_score,
    evaluate_dealer_group_duplicate,
    normalize_customer_name_for_similarity,
)


def _customer_bucket(
    nk: str,
    *,
    dealer_group_raw: str,
    source_samples: list[str] | None = None,
    source_norms: list[str] | None = None,
    dist_ids: set[int] | None = None,
) -> dict:
    return {
        "dealer_group_raw": dealer_group_raw,
        "source_customer_raw_samples": list(source_samples or []),
        "source_customer_evidence_norms": list(source_norms or []),
        "customer_evidence_norms": [],
        "sellout_distributor_ids": set(dist_ids or {1}),
        "row_count": 1,
        "total_units": 0,
        "total_value": 0,
        "samples": [],
    }


def test_exact_dealer_group_sets_dealer_group_exact_basis() -> None:
    ev = evaluate_dealer_group_duplicate("Acme Pty Ltd", "ACME PTY LTD")
    assert ev is not None
    assert ev.match_basis == "dealer_group_exact"
    assert ev.score >= 0.88


def test_short_normalized_whole_string_exact_only() -> None:
    from app.services.imports.dsi_customer_name_normalization import dsi_duplicate_similarity_score

    assert dsi_duplicate_similarity_score("TB", "TB") == 1.0
    assert dsi_duplicate_similarity_score("TB", "TA") is None


def test_tb_computers_vs_tb_solutions_no_dealer_group_hint() -> None:
    from app.services.imports.dsi_customer_name_normalization import dsi_duplicate_similarity_score

    assert dsi_duplicate_similarity_score("TB Computers", "TB Solutions") is None


def test_pc_world_vs_pc_direct_no_dealer_group_hint() -> None:
    from app.services.imports.dsi_customer_name_normalization import dsi_duplicate_similarity_score

    assert dsi_duplicate_similarity_score("PC World", "PC Direct") is None


def test_source_customer_exact_when_dealer_groups_differ() -> None:
    shared = normalize_customer_name_for_similarity("Outlet Alpha Store")
    agg = {
        ("customer_dealer_token", "group_a"): _customer_bucket(
            "group_a",
            dealer_group_raw="Zephyr Retail Holdings",
            source_norms=[shared],
            source_samples=["Outlet Alpha Store"],
        ),
        ("customer_dealer_token", "group_b"): _customer_bucket(
            "group_b",
            dealer_group_raw="Nimbus Wholesale Partners",
            source_norms=[shared],
            source_samples=["Outlet Alpha Store"],
        ),
    }
    annotate_dsi_customer_candidate_duplicates(agg, distributors=[])
    hints = agg[("customer_dealer_token", "group_a")].get("possible_duplicate_of")
    assert isinstance(hints, list) and len(hints) == 1
    assert hints[0]["normalized_key"] == "group_b"
    assert hints[0]["match_basis"] == "source_customer_exact"


def test_tb_pair_hints_via_source_customer_not_dealer_group() -> None:
    shared = normalize_customer_name_for_similarity("TB Retail Outlet")
    agg = {
        ("customer_dealer_token", "tb_comp"): _customer_bucket(
            "tb_comp",
            dealer_group_raw="TB Computers",
            source_norms=[shared],
            source_samples=["TB Retail Outlet"],
        ),
        ("customer_dealer_token", "tb_sol"): _customer_bucket(
            "tb_sol",
            dealer_group_raw="TB Solutions",
            source_norms=[shared],
            source_samples=["TB Retail Outlet"],
        ),
    }
    annotate_dsi_customer_candidate_duplicates(agg, distributors=[])
    hints = agg[("customer_dealer_token", "tb_comp")].get("possible_duplicate_of")
    assert isinstance(hints, list) and len(hints) == 1
    assert hints[0]["match_basis"] == "source_customer_exact"


def test_pc_world_vs_pc_direct_no_short_stem_dealer_hint() -> None:
    assert evaluate_dealer_group_duplicate("PC World", "PC Direct") is None


def test_bcs_computers_vs_rbs_computers_no_dealer_group_hint() -> None:
    assert evaluate_dealer_group_duplicate("BCS Computers", "RBS Computers") is None


def test_bcs_computers_vs_sbc_computers_no_dealer_group_hint() -> None:
    assert evaluate_dealer_group_duplicate("BCS Computers", "SBC Computers") is None


def test_bcs_computers_vs_bcs_computer_still_dealer_group_hint() -> None:
    ev = evaluate_dealer_group_duplicate("BCS Computers", "BCS Computer")
    assert ev is not None
    assert ev.match_basis in ("dealer_group_exact", "dealer_group_similar")
    assert ev.score >= 0.88


def test_spaced_acronym_bcs_vs_bcs_computers_still_hints() -> None:
    ev = evaluate_dealer_group_duplicate("B C S Computers", "BCS Computers")
    assert ev is not None
    assert ev.score >= 0.88


def test_bcs_vs_sbc_same_source_customer_source_exact_only() -> None:
    shared = normalize_customer_name_for_similarity("Outlet 99 Main Road")
    agg = {
        ("customer_dealer_token", "bcs"): _customer_bucket(
            "bcs",
            dealer_group_raw="BCS Computers",
            source_norms=[shared],
            source_samples=["Outlet 99 Main Road"],
        ),
        ("customer_dealer_token", "sbc"): _customer_bucket(
            "sbc",
            dealer_group_raw="SBC Computers",
            source_norms=[shared],
            source_samples=["Outlet 99 Main Road"],
        ),
    }
    annotate_dsi_customer_candidate_duplicates(agg, distributors=[])
    hints = agg[("customer_dealer_token", "bcs")].get("possible_duplicate_of")
    assert isinstance(hints, list) and len(hints) == 1
    assert hints[0]["normalized_key"] == "sbc"
    assert hints[0]["match_basis"] == "source_customer_exact"
    assert hints[0]["similarity_score"] == 1.0


def test_generic_source_customer_no_hint() -> None:
    agg = {
        ("customer_dealer_token", "a"): _customer_bucket(
            "a",
            dealer_group_raw="Group Alpha",
            source_norms=["cash sale"],
            source_samples=["Cash Sale"],
        ),
        ("customer_dealer_token", "b"): _customer_bucket(
            "b",
            dealer_group_raw="Group Beta",
            source_norms=["cash sale"],
            source_samples=["Cash Sale"],
        ),
    }
    annotate_dsi_customer_candidate_duplicates(agg, distributors=[])
    assert not agg[("customer_dealer_token", "a")].get("possible_duplicate_of")


def test_source_customer_matching_distributor_name_no_hint() -> None:
    dist = SimpleNamespace(id=7, name="Superior Support CC", code="SUP")
    norm = normalize_customer_name_for_similarity("Superior Support CC")
    agg = {
        ("customer_dealer_token", "a"): _customer_bucket(
            "a",
            dealer_group_raw="Account Alpha",
            source_norms=[norm],
        ),
        ("customer_dealer_token", "b"): _customer_bucket(
            "b",
            dealer_group_raw="Account Beta",
            source_norms=[norm],
        ),
    }
    annotate_dsi_customer_candidate_duplicates(agg, distributors=[dist])
    assert not agg[("customer_dealer_token", "a")].get("possible_duplicate_of")


def test_same_dealer_group_different_source_customers_no_hint() -> None:
    dg = "Acme Parent Group"
    agg = {
        ("customer_dealer_token", "branch_a"): _customer_bucket(
            "branch_a",
            dealer_group_raw=dg,
            source_norms=["acme jhb outlet"],
            source_samples=["Acme JHB Outlet"],
        ),
        ("customer_dealer_token", "branch_b"): _customer_bucket(
            "branch_b",
            dealer_group_raw=dg,
            source_norms=["acme cpt outlet"],
            source_samples=["Acme CPT Outlet"],
        ),
    }
    annotate_dsi_customer_candidate_duplicates(agg, distributors=[])
    assert not agg[("customer_dealer_token", "branch_a")].get("possible_duplicate_of")


def test_duplicate_review_required_still_gates_plan() -> None:
    cand = SimpleNamespace(
        entity_type="customer_dealer_token",
        context={
            "possible_duplicate_of": [
                {"normalized_key": "peer", "similarity_score": 1.0, "match_basis": "source_customer_exact"}
            ]
        },
    )
    assert dsi_candidate_duplicate_review_unresolved(cand) is True
    row = gate_dsi_plan_row_duplicate_review(cand, {"ready": True, "plan_status": "ready", "resolution_blockers": []})
    assert row["duplicate_review_required"] is True
    assert "duplicate_review_required" in row["resolution_blockers"]
