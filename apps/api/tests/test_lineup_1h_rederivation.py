"""Unit tests for 1H re-derivation preview logic (no cip writes)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.commercial_planner.lineup_bulk_rederivation import (
    HALF_YEAR_SIGNAL_FILENAME,
    HALF_YEAR_SIGNAL_MONTH_COLUMNS,
    HALF_YEAR_SIGNAL_WORKBOOK_SIBLING,
    build_1h_rederivation_collisions,
    case_has_1h_signal,
    lines_indicate_1h_month_phasing,
    resolve_half_year_signal,
)
from app.services.commercial_planner.lineup_half_year_quantity import half_year_allocation_summary


def test_case_has_1h_signal_from_filename():
    case = SimpleNamespace(file_name="ACZA 1H 2026 Consumer Lineup.xlsx")
    assert case_has_1h_signal(case)  # type: ignore[arg-type]


def test_rederivation_collision_lists_existing_and_twin():
    proposals = [
        {
            "proposal_key": "rederivation:35",
            "source_case_id": 35,
            "file_name": "1H file.xlsx",
            "q2_twin_proposal": {
                "proposal_key": "rederivation:35:q2",
                "supersession_group_key": "2026-04-01|makro|NB",
            },
            "q2_existing_collisions": [
                {"member_key": "existing:9", "case_id": 9, "file_name": "Q2 dedicated.xlsx"},
            ],
        }
    ]
    collisions = build_1h_rederivation_collisions(proposals)
    assert len(collisions) == 1
    assert collisions[0]["winner_member_key"] == "existing:9"
    assert len(collisions[0]["members"]) == 2


def test_makro_half_allocation_example():
    summary = half_year_allocation_summary(5678.0)
    assert summary["q1_allocated_units"] + summary["q2_allocated_units"] == 5678.0
    assert abs(summary["q1_allocated_units"] - 2839.0) < 1e-6


def test_lines_indicate_1h_from_stored_month_columns():
    line = SimpleNamespace(
        raw_row_payload={
            "uploaded": {"Jan": "10", "Feb": "5", "Apr": "8", "May": "2", "Qty": "25"},
        }
    )
    assert lines_indicate_1h_month_phasing([line])  # type: ignore[list-item]


def test_resolve_half_year_signal_workbook_sibling():
    nb_lines = [
        SimpleNamespace(
            raw_row_payload={"uploaded": {"Jan": "1", "Apr": "1"}},
        )
    ]
    nr_lines = [SimpleNamespace(raw_row_payload={"uploaded": {"Jan": "1", "Qty": "5"}})]
    workbook = "product lineup/nb/2025/q1/consumer.xlsx"
    nb_case = SimpleNamespace(file_name=workbook)
    nr_case = SimpleNamespace(file_name=workbook)
    keys = {workbook}
    ok_nb, src_nb = resolve_half_year_signal(
        nb_case, nb_lines, workbook_keys_with_direct_1h=keys  # type: ignore[arg-type]
    )
    ok_nr, src_nr = resolve_half_year_signal(
        nr_case, nr_lines, workbook_keys_with_direct_1h=keys  # type: ignore[arg-type]
    )
    assert ok_nb and src_nb == HALF_YEAR_SIGNAL_MONTH_COLUMNS
    assert ok_nr and src_nr == HALF_YEAR_SIGNAL_WORKBOOK_SIBLING


def test_q1_only_months_without_sibling_not_1h():
    case = SimpleNamespace(file_name="ACZA Q1 2025 Consumer Lineup.xlsx")
    lines = [SimpleNamespace(raw_row_payload={"uploaded": {"Jan": "1", "Feb": "2", "Qty": "3"}})]
    ok, src = resolve_half_year_signal(case, lines, workbook_keys_with_direct_1h=set())  # type: ignore[arg-type]
    assert not ok and src is None
    assert not case_has_1h_signal(case)  # type: ignore[arg-type]
