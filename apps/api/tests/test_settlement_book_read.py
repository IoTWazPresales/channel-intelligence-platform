"""Tests for NS-4 settlement book read model."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.cpor.settlement_book_read import build_settlement_book_read_model


def test_settlement_book_empty_cases():
    session = MagicMock()
    session.scalars.return_value.unique.return_value.all.return_value = []
    out = build_settlement_book_read_model(session)
    assert out["data_unavailable"] is False
    assert out["open_case_count"] == 0
    assert out["shape_segments"]["settled_pct"] == 0.0
    assert "No open settlement cases" in out["read_line"]
