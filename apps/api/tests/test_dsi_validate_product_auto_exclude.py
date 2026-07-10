"""Tests for DSI validate-time product auto-exclude (non-blocking catalogue/ambiguity)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_product_running_change import (
    AUTO_EXCLUDABLE_PRODUCT_ERROR_CODES,
    IGNORE_REASON_NO_CATALOGUE,
    IGNORE_REASON_NO_RECEIPT_EVIDENCE,
    IGNORE_REASON_SKU_INDETERMINATE,
    PRODUCT_HARD_BLOCK_ERROR_CODES,
    build_dsi_apply_exclusion_summary,
    compute_dsi_hard_row_with_product_auto_exclude,
    infer_validate_auto_exclude_product_reason,
    parse_steward_ignored_line_reason,
    product_auto_exclude_terminal_status,
    steward_ignored_line_diagnostic,
)


def test_auto_excludable_vs_hard_block_codes_disjoint() -> None:
    assert "missing_product_token" in PRODUCT_HARD_BLOCK_ERROR_CODES
    assert "unresolved_product" in AUTO_EXCLUDABLE_PRODUCT_ERROR_CODES
    assert AUTO_EXCLUDABLE_PRODUCT_ERROR_CODES.isdisjoint(PRODUCT_HARD_BLOCK_ERROR_CODES)


def test_no_catalogue_infer_reason() -> None:
    assert infer_validate_auto_exclude_product_reason("unresolved_product", None) == IGNORE_REASON_NO_CATALOGUE


def test_ambiguous_no_receipt_infer_reason() -> None:
    pev = SimpleNamespace(
        ambiguous_eligible={"product_ids": [1, 2], "tier": "sales_model_name"},
        receipt_disambiguation={"status": "no_receipt_evidence"},
        temporal_supersession=None,
    )
    assert (
        infer_validate_auto_exclude_product_reason("ambiguous_product_match", pev)
        == IGNORE_REASON_NO_RECEIPT_EVIDENCE
    )


def test_ambiguous_received_both_infer_sku_indeterminate() -> None:
    pev = SimpleNamespace(
        ambiguous_eligible={"product_ids": [1, 2]},
        receipt_disambiguation={"status": "ambiguous_overlap", "receipt_product_ids": [1, 2]},
        temporal_supersession={"fifo_candidate": True},
    )
    assert (
        infer_validate_auto_exclude_product_reason("ambiguous_product_match", pev)
        == IGNORE_REASON_SKU_INDETERMINATE
    )


def test_missing_product_token_not_auto_excluded() -> None:
    diag: list[str] = []
    hard_row, reason = compute_dsi_hard_row_with_product_auto_exclude(
        derr=None,
        rdid=1,
        perr="missing_product_token",
        rpid=None,
        pev=None,
        diag=diag,
    )
    assert reason is None
    assert hard_row is True
    assert not any(str(d).startswith("steward_ignored_line:") for d in diag)


def test_no_catalogue_softens_hard_row_and_tags_diagnostic() -> None:
    diag: list[str] = []
    hard_row, reason = compute_dsi_hard_row_with_product_auto_exclude(
        derr=None,
        rdid=1,
        perr="unresolved_product",
        rpid=None,
        pev=None,
        diag=diag,
    )
    assert reason == IGNORE_REASON_NO_CATALOGUE
    assert hard_row is False
    assert steward_ignored_line_diagnostic(IGNORE_REASON_NO_CATALOGUE) in diag
    sev, res_status = product_auto_exclude_terminal_status()
    assert sev == "info"
    assert res_status == "staged_only"


def test_distributor_error_still_hard_blocks_with_auto_excluded_product() -> None:
    diag: list[str] = []
    hard_row, reason = compute_dsi_hard_row_with_product_auto_exclude(
        derr="unresolved_distributor_token",
        rdid=None,
        perr="unresolved_product",
        rpid=None,
        pev=None,
        diag=diag,
    )
    assert reason == IGNORE_REASON_NO_CATALOGUE
    assert hard_row is True


def test_apply_exclusion_counts_auto_excluded_validate_lines() -> None:
    class _Line:
        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    tag = steward_ignored_line_diagnostic(IGNORE_REASON_NO_CATALOGUE)
    lines = [
        _Line(
            resolved_product_id=None,
            quantity_sold=4,
            reported_revenue_amount=40.0,
            diagnostic_codes=[tag, "unresolved_product"],
            raw_product_token="NOPE",
        ),
    ]

    class _Db:
        def scalars(self, _stmt: object) -> object:
            return self

        def all(self) -> list[object]:
            return []

    summary = build_dsi_apply_exclusion_summary(_Db(), 1, lines)  # type: ignore[arg-type]
    assert summary["excluded_line_count"] == 1
    assert summary["excluded_units"] == 4.0
    assert summary["excluded_value"] == 40.0
    assert parse_steward_ignored_line_reason([tag]) == IGNORE_REASON_NO_CATALOGUE
    assert summary["excluded_by_reason"][IGNORE_REASON_NO_CATALOGUE]["line_count"] == 1
