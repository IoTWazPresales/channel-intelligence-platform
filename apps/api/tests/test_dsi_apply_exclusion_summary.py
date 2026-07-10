"""Tests for DSI steward-ignore staging demotion and apply-exclusion reporting."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_product_running_change import (
    IGNORE_REASON_NO_CATALOGUE,
    IGNORE_REASON_NO_RECEIPT_EVIDENCE,
    IGNORE_REASON_SKU_INDETERMINATE,
    build_dsi_apply_exclusion_summary,
    demote_staging_line_for_steward_product_ignore,
    infer_dsi_ignore_reason_code,
    parse_steward_ignored_line_reason,
    steward_ignored_line_diagnostic,
)


def test_infer_no_receipt_evidence_reason() -> None:
    ctx = {
        "product_match_status": "ambiguous_eligible",
        "product_ambiguous_eligible": {"product_ids": [10, 20]},
        "receipt_disambiguation": {"status": "no_receipt_evidence"},
    }
    assert infer_dsi_ignore_reason_code(ctx) == IGNORE_REASON_NO_RECEIPT_EVIDENCE


def test_demote_staging_line_does_not_touch_resolved_product() -> None:
    resolved = SimpleNamespace(
        resolved_product_id=99,
        diagnostic_codes=["ambiguous_product_match"],
        resolution_status="ready_sellout",
        severity="info",
    )
    demote_staging_line_for_steward_product_ignore(resolved, IGNORE_REASON_SKU_INDETERMINATE)
    assert resolved.resolution_status == "ready_sellout"
    assert resolved.resolved_product_id == 99

    unresolved = SimpleNamespace(
        resolved_product_id=None,
        diagnostic_codes=["ambiguous_product_match"],
        resolution_status="blocked",
        severity="error",
    )
    demote_staging_line_for_steward_product_ignore(unresolved, IGNORE_REASON_SKU_INDETERMINATE)
    assert unresolved.resolution_status == "staged_only"
    assert unresolved.severity == "info"
    assert steward_ignored_line_diagnostic(IGNORE_REASON_SKU_INDETERMINATE) in (unresolved.diagnostic_codes or [])
    assert parse_steward_ignored_line_reason(unresolved.diagnostic_codes) == IGNORE_REASON_SKU_INDETERMINATE


def test_apply_exclusion_summary_splits_by_reason() -> None:
    class _Line:
        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    lines = [
        _Line(
            resolved_product_id=1,
            resolved_distributor_id=1,
            resolved_customer_id=1,
            transaction_date="2025-01-01",
            quantity_sold=2,
            computed_revenue_amount=10.0,
            diagnostic_codes=[],
            raw_product_token="SKU-A",
        ),
        _Line(
            resolved_product_id=None,
            quantity_sold=5,
            reported_revenue_amount=25.0,
            diagnostic_codes=[steward_ignored_line_diagnostic(IGNORE_REASON_NO_CATALOGUE)],
            raw_product_token="NO-CAT",
        ),
        _Line(
            resolved_product_id=None,
            quantity_sold=3,
            computed_revenue_amount=9.0,
            diagnostic_codes=["unresolved_product"],
            raw_product_token="UNKNOWN",
        ),
    ]

    class _Db:
        def scalars(self, _stmt: object) -> object:
            return self

        def all(self) -> list[object]:
            return []

    summary = build_dsi_apply_exclusion_summary(_Db(), 1, lines)  # type: ignore[arg-type]
    assert summary["applied_line_count"] == 1
    assert summary["applied_units"] == 2.0
    assert summary["excluded_line_count"] == 2
    assert summary["excluded_units"] == 8.0
    assert summary["excluded_by_reason"][IGNORE_REASON_NO_CATALOGUE]["line_count"] == 2
