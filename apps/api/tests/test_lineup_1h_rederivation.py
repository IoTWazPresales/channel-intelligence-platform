"""Unit tests for 1H re-derivation preview logic (no cip writes)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.commercial_planner.lineup_bulk_rederivation import (
    build_1h_rederivation_collisions,
    case_has_1h_signal,
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
