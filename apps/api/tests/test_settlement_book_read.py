"""Tests for NS-4 settlement book read model."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.cpor.settlement_book_read import build_settlement_book_read_model, shape_segment_pcts


def test_settlement_book_empty_cases():
    session = MagicMock()
    session.scalars.return_value.unique.return_value.all.return_value = []
    out = build_settlement_book_read_model(session)
    assert out["data_unavailable"] is False
    assert out["open_case_count"] == 0
    assert out["shape_segments"]["settled_pct"] == 0.0
    assert "No open settlement cases" in out["read_line"]
    assert out["by_evidence_basis"]["none"]["case_count"] == 0


def test_shape_segments_cap_blocked_so_bar_cannot_exceed_book():
    """Live cip 2026-09-04: book 6021148.88, blocked 6022199.36, outstanding 6021148.88, paid 0."""
    segs = shape_segment_pcts(
        book_total=6_021_148.88,
        settled_amount=0.0,
        outstanding_amount=6_021_148.88,
        blocked_amount=6_022_199.36,
    )
    assert segs["settled_pct"] == 0.0
    assert segs["outstanding_pct"] == 0.0
    assert segs["blocked_pct"] == 100.0
    assert segs["settled_pct"] + segs["outstanding_pct"] + segs["blocked_pct"] == 100.0
