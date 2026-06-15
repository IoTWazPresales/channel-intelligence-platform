"""Unit tests for aggregated DSI candidate tab counts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.imports.dsi_mapping_candidates_tab_counts import dsi_mapping_candidate_tab_counts_sync


def test_tab_counts_aggregates_open_and_needs_review() -> None:
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(
            all=MagicMock(
                return_value=[
                    ("distributor_token", "open", 5),
                    ("distributor_token", "needs_review", 2),
                    ("distributor_token", "resolved", 10),
                    ("customer_dealer_token", "open", 100),
                    ("customer_dealer_token", "needs_review", 7),
                    ("product_identifier", "ignored", 3),
                    ("product_identifier", "open", 12),
                ]
            )
        ),
        MagicMock(all=MagicMock(return_value=[])),
    ]

    out = dsi_mapping_candidate_tab_counts_sync(session, 43)

    assert out["import_job_id"] == 43
    assert out["counts"]["distributor"]["open"] == 7
    assert out["counts"]["distributor"]["needs_review"] == 2
    assert out["counts"]["customer"]["open"] == 107
    assert out["counts"]["customer"]["needs_review"] == 7
    assert out["counts"]["product"]["open"] == 12
    assert out["counts"]["product"]["needs_review"] == 0
    assert out["counts"]["product"]["no_match"] == 0
    assert out["counts"]["product"]["ambiguous_eligible"] == 0


def test_tab_counts_includes_product_match_status_breakdown() -> None:
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(
            all=MagicMock(
                return_value=[
                    ("product_identifier", "open", 361),
                ]
            )
        ),
        MagicMock(
            all=MagicMock(
                return_value=[
                    ("no_match", 296),
                    ("ambiguous_eligible", 65),
                ]
            )
        ),
    ]

    out = dsi_mapping_candidate_tab_counts_sync(session, 43)

    assert out["counts"]["product"]["no_match"] == 296
    assert out["counts"]["product"]["ambiguous_eligible"] == 65
