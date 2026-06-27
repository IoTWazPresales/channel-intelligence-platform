"""DSI apply gate: human-fixable blockers only; structural master-data exclusions do not gate."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_apply_completion import DsiApplyCompletionError, complete_dsi_import_job_to_loaded
from app.services.imports.dsi_product_running_change import (
    IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT,
    IGNORE_REASON_NO_CUSTOMER,
    build_dsi_apply_exclusion_summary,
    compute_dsi_sellout_block_with_customer_auto_exclude,
    infer_validate_auto_exclude_alias_scope_reason,
    is_human_fixable_dsi_blocked_staging_line,
    product_auto_exclude_terminal_status,
    steward_ignored_line_diagnostic,
)


def test_alias_scope_conflict_infer_structural_exclude() -> None:
    assert (
        infer_validate_auto_exclude_alias_scope_reason(
            sellout_or_return_attempt=True,
            cust_diag=["multiple_approved_customer_aliases_for_token"],
        )
        == IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT
    )


def test_alias_scope_conflict_demotes_sellout_block() -> None:
    diag: list[str] = []
    blocked, reason = compute_dsi_sellout_block_with_customer_auto_exclude(
        sellout_or_return_attempt=True,
        rcustomer_id=None,
        cust_diag=["multiple_approved_customer_aliases_for_token", "customer_unresolved"],
        normalized_candidate_key="vexall",
        customer_dealer_raw="VEXALL",
        dealer_group_raw="vexall",
        diag=diag,
    )
    assert blocked is False
    assert reason == IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT
    assert steward_ignored_line_diagnostic(IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT) in diag


def test_real_unmapped_customer_still_human_fixable_blocked() -> None:
    line = SimpleNamespace(
        resolution_status="blocked",
        diagnostic_codes=["customer_unresolved", "sellout_blocked_missing_customer"],
    )
    assert is_human_fixable_dsi_blocked_staging_line(line) is True


def test_structural_master_data_exclude_not_human_fixable() -> None:
    line = SimpleNamespace(
        resolution_status="blocked",
        diagnostic_codes=[
            steward_ignored_line_diagnostic(IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT),
        ],
    )
    assert is_human_fixable_dsi_blocked_staging_line(line) is False


def test_auto_excluded_no_customer_not_human_fixable() -> None:
    line = SimpleNamespace(
        resolution_status="staged_only",
        diagnostic_codes=[steward_ignored_line_diagnostic(IGNORE_REASON_NO_CUSTOMER)],
        quantity_sold=1,
        stock_on_hand=None,
        resolved_product_id=1,
        resolved_distributor_id=1,
        resolved_customer_id=None,
        transaction_date="2024-01-01",
        snapshot_date=None,
        unit_sellout_price_ex_tax_amount=None,
        reported_revenue_amount=None,
    )
    assert is_human_fixable_dsi_blocked_staging_line(line) is False


def test_apply_exclusion_summary_includes_master_data_bucket() -> None:
    line = SimpleNamespace(
        resolution_status="staged_only",
        diagnostic_codes=[
            steward_ignored_line_diagnostic(IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT),
        ],
        quantity_sold=5,
        stock_on_hand=None,
        resolved_product_id=10,
        resolved_distributor_id=1,
        resolved_customer_id=None,
        transaction_date="2024-01-01",
        snapshot_date=None,
        unit_sellout_price_ex_tax_amount=None,
        reported_revenue_amount=None,
        raw_product_token="sku-1",
    )
    ready = SimpleNamespace(
        resolution_status="ready_inventory",
        diagnostic_codes=[],
        quantity_sold=None,
        stock_on_hand=100,
        resolved_product_id=10,
        resolved_distributor_id=1,
        resolved_customer_id=None,
        transaction_date=None,
        snapshot_date="2024-06-01",
        unit_sellout_price_ex_tax_amount=None,
        reported_revenue_amount=None,
        raw_product_token="sku-1",
    )

    class _FakeDb:
        def scalars(self, _q):
            return SimpleNamespace(all=lambda: [])

    summary = build_dsi_apply_exclusion_summary(_FakeDb(), 1, [line, ready])  # type: ignore[arg-type]
    bucket = summary["excluded_by_reason"].get(IGNORE_REASON_MASTER_DATA_ALIAS_SCOPE_CONFLICT)
    assert bucket is not None
    assert int(bucket["line_count"]) == 1
    assert int(summary["applied_line_count"]) == 1


def test_complete_dsi_apply_raises_on_human_fixable_blocked(monkeypatch) -> None:
    blocked_line = SimpleNamespace(
        source_row_number=42,
        resolution_status="blocked",
        diagnostic_codes=["customer_unresolved"],
    )
    job = SimpleNamespace(
        id=1,
        template_slug="distributor_inventory",
        stage="validated",
        import_mode="apply",
        staged_metadata={},
    )

    class _FakeDb:
        def get(self, _model, _id):
            return job

        def scalars(self, _q):
            return SimpleNamespace(all=lambda: [blocked_line])

        def flush(self):
            return None

        def add(self, _x):
            return None

        def commit(self):
            return None

        def refresh(self, _x):
            return None

        def scalar(self, _q):
            return None

    monkeypatch.setattr(
        "app.services.imports.dsi_apply_completion._load_product_resolution_index",
        lambda _db: {},
    )
    monkeypatch.setattr(
        "app.services.imports.dsi_apply_completion.refresh_dsi_staging_line_resolution",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.services.imports.dsi_product_running_change.reapply_dsi_steward_ignored_product_staging_lines",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.services.imports.dsi_product_running_change.reapply_dsi_steward_ignored_customer_staging_lines",
        lambda *_a, **_k: None,
    )

    import pytest

    with pytest.raises(DsiApplyCompletionError) as exc:
        complete_dsi_import_job_to_loaded(_FakeDb(), 1)  # type: ignore[arg-type]
    assert "human-fixable blocked" in str(exc.value).lower()
