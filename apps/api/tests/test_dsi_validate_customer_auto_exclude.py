"""Tests for DSI validate-time customer auto-exclude (blank/placeholder sellout only)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_product_running_change import (
    IGNORE_REASON_NO_CUSTOMER,
    build_dsi_apply_exclusion_summary,
    compute_dsi_sellout_block_with_customer_auto_exclude,
    demote_staging_line_for_steward_customer_ignore,
    infer_validate_auto_exclude_customer_reason,
    parse_steward_ignored_line_reason,
    product_auto_exclude_terminal_status,
    steward_ignored_line_diagnostic,
)


def test_blank_candidate_key_infer_ignore_no_customer() -> None:
    assert (
        infer_validate_auto_exclude_customer_reason(
            sellout_or_return_attempt=True,
            rcustomer_id=None,
            cust_diag=["missing_customer_token"],
            normalized_candidate_key="__blank__",
        )
        == IGNORE_REASON_NO_CUSTOMER
    )


def test_to_be_mapped_dealer_group_infer_ignore_no_customer() -> None:
    assert (
        infer_validate_auto_exclude_customer_reason(
            sellout_or_return_attempt=True,
            rcustomer_id=None,
            cust_diag=["dealer_group_placeholder", "missing_customer_token"],
            normalized_candidate_key="__blank__",
            customer_dealer_raw="",
            dealer_group_raw="to be mapped",
        )
        == IGNORE_REASON_NO_CUSTOMER
    )


def test_real_unmapped_customer_not_auto_excluded() -> None:
    assert (
        infer_validate_auto_exclude_customer_reason(
            sellout_or_return_attempt=True,
            rcustomer_id=None,
            cust_diag=["customer_unresolved"],
            normalized_candidate_key="itech administrators pty ltd",
            customer_dealer_raw="ITECH",
            dealer_group_raw="itech administrators pty ltd",
        )
        is None
    )


def test_blank_sellout_softens_block_and_tags_diagnostic() -> None:
    diag: list[str] = []
    blocked, reason = compute_dsi_sellout_block_with_customer_auto_exclude(
        sellout_or_return_attempt=True,
        rcustomer_id=None,
        cust_diag=["dealer_group_placeholder", "missing_customer_token"],
        normalized_candidate_key="__blank__",
        customer_dealer_raw="",
        dealer_group_raw="to be mapped",
        diag=diag,
    )
    assert reason == IGNORE_REASON_NO_CUSTOMER
    assert blocked is False
    assert steward_ignored_line_diagnostic(IGNORE_REASON_NO_CUSTOMER) in diag
    sev, res_status = product_auto_exclude_terminal_status()
    assert sev == "info"
    assert res_status == "staged_only"


def test_real_unmapped_customer_stays_blocked() -> None:
    diag: list[str] = []
    blocked, reason = compute_dsi_sellout_block_with_customer_auto_exclude(
        sellout_or_return_attempt=True,
        rcustomer_id=None,
        cust_diag=["customer_unresolved"],
        normalized_candidate_key="itech administrators pty ltd",
        customer_dealer_raw="ITECH",
        dealer_group_raw="itech administrators pty ltd",
        diag=diag,
    )
    assert reason is None
    assert blocked is True
    assert not any(str(d).startswith("steward_ignored_line:") for d in diag)


def test_demote_customer_line_does_not_clear_resolved_customer_id() -> None:
    line = SimpleNamespace(
        resolved_customer_id=42,
        diagnostic_codes=["sellout_blocked_missing_customer"],
        resolution_status="ready_sellout",
        severity="info",
    )
    demote_staging_line_for_steward_customer_ignore(line, IGNORE_REASON_NO_CUSTOMER)
    assert line.resolved_customer_id == 42
    assert steward_ignored_line_diagnostic(IGNORE_REASON_NO_CUSTOMER) in line.diagnostic_codes
    assert line.resolution_status == "staged_only"
    assert line.severity == "info"


def test_apply_exclusion_summary_includes_customer_bucket() -> None:
    class _Line:
        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    tag = steward_ignored_line_diagnostic(IGNORE_REASON_NO_CUSTOMER)
    lines = [
        _Line(
            resolved_product_id=99,
            resolved_distributor_id=1,
            resolved_customer_id=None,
            transaction_date="2025-01-01",
            quantity_sold=3,
            reported_revenue_amount=30.0,
            diagnostic_codes=[tag, "missing_customer_token"],
            raw_product_token="SKU-1",
            raw_customer_dealer_token="",
            raw_dealer_group_token="to be mapped",
        ),
    ]

    class _Db:
        def scalars(self, _stmt: object) -> object:
            return self

        def all(self) -> list[object]:
            return []

    summary = build_dsi_apply_exclusion_summary(_Db(), 1, lines)  # type: ignore[arg-type]
    assert summary["excluded_line_count"] == 1
    assert summary["excluded_units"] == 3.0
    assert summary["excluded_value"] == 30.0
    assert summary["excluded_by_reason"][IGNORE_REASON_NO_CUSTOMER]["line_count"] == 1
    assert parse_steward_ignored_line_reason([tag]) == IGNORE_REASON_NO_CUSTOMER
