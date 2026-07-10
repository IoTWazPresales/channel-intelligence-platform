"""Tests for uniform half-year quantity allocation."""

from app.services.commercial_planner.lineup_half_year_quantity import (
    HALF_YEAR_ALLOCATION_FLAG,
    allocate_uniform_half,
    apply_half_year_allocation_to_row_dict,
    half_year_allocation_summary,
)


def test_sum_invariance_odd_quantity():
    summary = half_year_allocation_summary(15.0)
    assert summary["q1_allocated_units"] == 8.0
    assert summary["q2_allocated_units"] == 7.0
    assert summary["sum_invariant"] is True


def test_sum_invariance_even_quantity():
    summary = half_year_allocation_summary(100.0)
    assert summary["q1_allocated_units"] == 50.0
    assert summary["q2_allocated_units"] == 50.0
    assert summary["sum_invariant"] is True


def test_allocate_uniform_half_per_line():
    assert allocate_uniform_half(11.0, half="q1") == 6.0
    assert allocate_uniform_half(11.0, half="q2") == 5.0


def test_row_dict_allocation_flags_and_preserves_source():
    row = apply_half_year_allocation_to_row_dict(
        {"quantity_units": 9.0, "dap_evidence_local": 100.0, "diagnostic_codes": []},
        half="q1",
    )
    assert row["quantity_units"] == 5.0
    assert row["dap_evidence_local"] == 50.0
    assert HALF_YEAR_ALLOCATION_FLAG in row["diagnostic_codes"]
    assert row["raw_row_payload"]["half_year_source_quantity_units"] == 9.0
