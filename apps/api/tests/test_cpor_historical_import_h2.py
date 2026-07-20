"""CPOR H2 — unit tests (no cip writes)."""

from __future__ import annotations

from datetime import date

from app.models.cpor_historical import ImportCporHistoricalStagingLine
from app.services.cpor.historical_import.resolve import case_apply_blockers
from app.services.cpor.historical_import.staging import _row_to_values
from app.services.imports.import_background_slots import (
    KIND_CPOR_HISTORICAL_IMPORT,
    _kind_from_template_slug,
    task_label,
)
from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS


def test_template_handler_not_stub():
    row = next(r for r in IMPORT_TEMPLATE_ROWS if r["slug"] == "cpor_historical_cases")
    assert row["pipeline_handler"] == "cpor_historical_cases_import"
    assert row["destructive_apply_requires_confirm"] is True
    assert row["hidden"] is True


def test_background_slot_kind_for_historical():
    job = type("J", (), {"id": 42, "template_slug": "cpor_historical_cases", "import_mode": "apply"})()
    assert _kind_from_template_slug(job) == KIND_CPOR_HISTORICAL_IMPORT
    assert "historical cpor" in task_label(job, kind=KIND_CPOR_HISTORICAL_IMPORT).lower()


def test_case_apply_blockers_unresolved_and_flags():
    row = ImportCporHistoricalStagingLine(
        import_job_id=1,
        source_key="k",
        source_row_number=1,
        sheet_name="Reseller Sell out",
        channel="reseller",
        case_code="C1",
        customer_token="Acme",
        sales_model_token="MODEL",
        distributor_token="Disti",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
        flags_json={"flags": ["waterfall_parity_variance", "case_code_collision_native"]},
        raw_source_row={},
    )
    blockers = case_apply_blockers(row)
    assert "case_code_collision_native" in blockers
    assert "unresolved_product" in blockers
    assert "unresolved_customer" in blockers
    assert "unresolved_distributor" in blockers
    # Parity alone must NOT be a blocker
    assert "waterfall_parity_variance" not in blockers


def test_case_apply_blockers_clear_when_resolved():
    row = ImportCporHistoricalStagingLine(
        import_job_id=1,
        source_key="k",
        source_row_number=1,
        sheet_name="Reseller Sell out",
        channel="reseller",
        case_code="C1",
        resolved_customer_id=1,
        resolved_product_id=2,
        resolved_distributor_id=3,
        distributor_token="Disti",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
        flags_json={"flags": ["waterfall_parity_variance"]},
        raw_source_row={},
    )
    assert case_apply_blockers(row) == []


def test_staging_row_to_values_preserves_flags_and_snapshot():
    vals = _row_to_values(
        9,
        {
            "source_key": "abc",
            "source_row_number": 2,
            "sheet_name": "Disti Sell out",
            "channel": "disti",
            "case_code": "X",
            "flags_json": {"flags": ["ttl_result_mismatch"]},
            "source_snapshot_json": {"Result": 8},
            "raw_source_row": {"Case ID": "X"},
            "skip_apply": False,
        },
    )
    assert vals["import_job_id"] == 9
    assert vals["source_key"] == "abc"
    assert vals["flags_json"]["flags"] == ["ttl_result_mismatch"]
    assert vals["source_snapshot_json"]["Result"] == 8
    assert vals["raw_source_row"]["Case ID"] == "X"
