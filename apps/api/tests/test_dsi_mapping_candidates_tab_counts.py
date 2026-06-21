"""Unit tests for aggregated DSI candidate tab counts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.imports.dsi_mapping_candidates_tab_counts import (
    dsi_mapping_candidate_tab_counts_sync,
    product_match_status_count_stmt,
)


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
    assert out["counts"]["distributor"]["needs_work"] == 7
    assert out["counts"]["distributor"]["needs_review"] == 2
    assert out["counts"]["customer"]["open"] == 107
    assert out["counts"]["customer"]["needs_work"] == 107
    assert out["counts"]["customer"]["needs_review"] == 7
    assert out["counts"]["product"]["open"] == 12
    assert out["counts"]["product"]["needs_work"] == 12
    assert out["counts"]["product"]["needs_review"] == 0
    assert out["counts"]["product"]["no_match"] == 0
    assert out["counts"]["product"]["ambiguous_eligible"] == 0


def test_tab_counts_excludes_terminal_resolved_and_ignored_from_needs_work() -> None:
    """Job #43-style customer tab: terminal rows must not inflate open / needs_work."""
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(
            all=MagicMock(
                return_value=[
                    ("customer_dealer_token", "resolved", 6),
                    ("customer_dealer_token", "ignored", 1),
                    ("customer_dealer_token", "needs_review", 0),
                ]
            )
        ),
        MagicMock(all=MagicMock(return_value=[])),
    ]

    out = dsi_mapping_candidate_tab_counts_sync(session, 43)

    assert out["counts"]["customer"]["open"] == 0
    assert out["counts"]["customer"]["needs_work"] == 0
    assert out["counts"]["customer"]["needs_review"] == 0


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


def test_product_match_status_count_stmt_groups_by_labeled_select_expression() -> None:
    """GROUP BY must reuse the SELECT JSONB expression (avoid duplicate bind params)."""
    from sqlalchemy.dialects import postgresql

    stmt = product_match_status_count_stmt(job_id=43)
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    params = compiled.params
    assert "GROUP BY" in sql
    assert "product_match_status" in sql
    # One bind key for the JSON path — not two independent context->>$N fragments.
    context_param_keys = [k for k in params if k.startswith("context")]
    assert len(context_param_keys) == 1
