"""Unit tests for DSI running-change display + ignore disposition helpers."""

from __future__ import annotations

from app.services.imports.dsi_product_running_change import (
    IGNORE_REASON_NO_CATALOGUE,
    IGNORE_REASON_NO_RECEIPT_EVIDENCE,
    IGNORE_REASON_SKU_INDETERMINATE,
    accumulate_product_running_change_stat,
    build_product_resolution_quality,
    build_steward_ignore_remap_context,
    enrich_product_candidate_running_change_context,
    format_running_change_match_summary,
    infer_dsi_ignore_reason_code,
    is_dsi_running_change_ambiguous_context,
    new_product_running_change_stats_bucket,
    strip_ambiguous_product_match_from_diags,
)


def test_strip_ambiguous_product_match_from_diags() -> None:
    diag = ["ambiguous_product_match", "customer_resolved_alias"]
    prod_diag = ["ambiguous_product_match", "distributor_receipt_single"]
    strip_ambiguous_product_match_from_diags(diag, prod_diag)
    assert "ambiguous_product_match" not in prod_diag
    assert "ambiguous_product_match" not in diag
    assert "customer_resolved_alias" in diag
    assert "distributor_receipt_single" in prod_diag


def test_running_change_summary_from_stats() -> None:
    stats = new_product_running_change_stats_bucket()
    for _ in range(5):
        accumulate_product_running_change_stat(
            stats, resolved_product_id=1, presolve_tag="distributor_receipt_single"
        )
    for _ in range(2):
        accumulate_product_running_change_stat(stats, resolved_product_id=None, presolve_tag=None)
    ctx: dict = {
        "product_match_status": "ambiguous_eligible",
        "product_ambiguous_eligible": {"product_ids": [10, 20], "tier": "sales_model_name"},
        "receipt_disambiguation": {"status": "ambiguous_overlap", "receipt_product_ids": [10, 20]},
        "fifo_candidate": True,
    }
    enrich_product_candidate_running_change_context(ctx, stats)
    assert ctx["product_resolution_quality"]["total_rows"] == 7
    assert ctx["product_resolution_quality"]["resolved_receipt_temporal"] == 5
    assert ctx["product_resolution_quality"]["indeterminate_rows"] == 2
    assert "5 of 7 resolved by shipment receipt/temporal" in ctx["product_match_summary"]
    assert "(received-both)" in ctx["product_match_summary"]


def test_ignore_reason_inference() -> None:
    amb_ctx = {
        "product_match_status": "ambiguous_eligible",
        "product_ambiguous_eligible": {"product_ids": [1, 2]},
        "receipt_disambiguation": {"status": "ambiguous_overlap", "receipt_product_ids": [1, 2]},
    }
    assert infer_dsi_ignore_reason_code(amb_ctx) == IGNORE_REASON_SKU_INDETERMINATE
    assert infer_dsi_ignore_reason_code({"product_match_status": "no_match"}) == IGNORE_REASON_NO_CATALOGUE
    no_receipt = {
        "product_match_status": "ambiguous_eligible",
        "product_ambiguous_eligible": {"product_ids": [1, 2]},
        "receipt_disambiguation": {"status": "no_receipt_evidence"},
    }
    assert infer_dsi_ignore_reason_code(no_receipt) == IGNORE_REASON_NO_RECEIPT_EVIDENCE


def test_is_running_change_blocks_token_alias() -> None:
    ctx = {
        "product_match_status": "ambiguous_eligible",
        "product_ambiguous_eligible": {"product_ids": [10, 20]},
        "receipt_disambiguation": {"status": "ambiguous_overlap"},
    }
    assert is_dsi_running_change_ambiguous_context(ctx) is True


def test_ignore_remap_context_preserves_evidence() -> None:
    ctx = {
        "product_ambiguous_eligible": {"product_ids": [1, 2]},
        "receipt_disambiguation": {"status": "ambiguous_overlap"},
        "temporal_supersession": {"fifo_candidate": True},
        "product_resolution_quality": {"total_rows": 10},
    }
    remap = build_steward_ignore_remap_context(ctx)
    assert "receipt_disambiguation" in remap
    assert "product_resolution_quality" in remap


def test_quality_denominator_excludes_ignored() -> None:
    q = build_product_resolution_quality(
        {"total_rows": 100, "resolved_receipt_temporal": 40, "resolved_other": 0, "unresolved_rows": 60},
        ignored_rows=25,
    )
    assert q["ignored_rows"] == 25
    assert q["quality_denominator"] == 75
    assert q["indeterminate_rows"] == 35
    summary = format_running_change_match_summary(q, received_both=True)
    assert "40 of 100" in summary
    assert "35 indeterminate" in summary
