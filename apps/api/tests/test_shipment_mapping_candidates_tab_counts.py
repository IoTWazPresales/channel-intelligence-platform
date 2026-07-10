"""Tests for shipment mapping candidate tab counts."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.imports.shipment_mapping_candidates_tab_counts import shipment_mapping_candidate_tab_counts_sync


def test_shipment_tab_counts_aggregates():
    session = MagicMock()
    session.execute.return_value = MagicMock(
        all=MagicMock(
            return_value=[
                ("shipment_distributor", "needs_review", 2),
                ("shipment_distributor", "resolved", 5),
                ("shipment_customer_token", "open", 3),
            ]
        )
    )
    out = shipment_mapping_candidate_tab_counts_sync(session, 42)
    assert out["import_job_id"] == 42
    assert out["counts"]["distributor"]["open"] == 2
    assert out["counts"]["distributor"]["needs_review"] == 2
    assert out["counts"]["customer"]["open"] == 3
