"""Unit tests for layered bulk lineup period inference."""

from datetime import date

from app.services.commercial_planner.lineup_bulk_period_inference import (
    resolve_layered_period,
    scan_title_band_from_workbook_rows,
)


def test_half_year_splits_to_q1_q2():
    assignments, report = resolve_layered_period(
        filename="1. ACZA 2026 1H NEW PLAN.xlsx",
        title_band="2026 1H NEW PLAN",
    )
    assert len(assignments) == 2
    assert assignments[0].period_start == date(2026, 1, 1)
    assert assignments[1].period_start == date(2026, 4, 1)
    assert "period_half_split_q1" in assignments[0].flags
    assert report["winning_tier"] == "title_band"


def test_folder_path_quarter():
    assignments, _ = resolve_layered_period(folder_path=r"NB\2025\Q3\file.xlsx")
    assert len(assignments) == 1
    assert assignments[0].period_start == date(2025, 7, 1)
    assert assignments[0].source_tier == "folder"


def test_title_filename_conflict_flags():
    assignments, report = resolve_layered_period(
        folder_path=r"NR\2025\Q3",
        filename="ACZA Q4 2025 Consumer.xlsx",
    )
    assert len(assignments) == 1
    assert assignments[0].period_start is None
    assert "period_signal_conflict" in assignments[0].flags
    assert "conflict" in report


def test_scan_title_band_from_rows():
    rows = [[None, "2025 Q2 NEW PLAN", None], ["SKU", "Qty"]]
    assert scan_title_band_from_workbook_rows(rows) == "2025 Q2 NEW PLAN"
