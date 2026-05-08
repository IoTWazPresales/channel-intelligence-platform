"""Tests for shipment evidence canonical text normalization (formula literals, text apostrophe)."""

from __future__ import annotations

import pytest

from app.services.imports.shipment_evidence_text_normalize import (
    normalize_shipment_cell_value,
    normalize_shipment_text_field,
    unwrap_excel_double_quoted_literal,
)


def test_unwrap_mid_formula_first_quoted_literal() -> None:
    s = '=MID("151126001",1,9)'
    assert unwrap_excel_double_quoted_literal(s) == "151126001"


def test_unwrap_mid_with_comma_args() -> None:
    s = '=MID("SO-999",2,5)'
    assert unwrap_excel_double_quoted_literal(s) == "SO-999"


def test_unwrap_escaped_quote_inside_literal() -> None:
    s = '=MID("ACME ""HQ""",1,20)'
    out = unwrap_excel_double_quoted_literal(s)
    assert out == 'ACME "HQ"'


def test_non_formula_returns_none_from_unwrap() -> None:
    assert unwrap_excel_double_quoted_literal("plain") is None


def test_leading_apostrophe_text_preservation() -> None:
    assert normalize_shipment_text_field("'00123") == "00123"


def test_normalize_order_like_mid() -> None:
    assert normalize_shipment_text_field('=MID("PO-42",1,99)') == "PO-42"


def test_normalize_cell_int_preserves_digits() -> None:
    assert normalize_shipment_cell_value(1500123) == "1500123"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        ("nan", None),
    ],
)
def test_normalize_empty(raw: str, expected: str | None) -> None:
    assert normalize_shipment_text_field(raw) == expected
