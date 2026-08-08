"""BACKLOG-076 — unit-price scale suspect helper + SQL clause shape."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.facts import FactInboundShipment
from app.services.shipping.amount_scale import (
    UNIT_PRICE_SUSPECT_THRESHOLD,
    amount_scale_not_suspect_clause,
    amount_scale_suspect_clause,
    is_unit_price_scale_suspect,
)


def test_threshold_value() -> None:
    assert UNIT_PRICE_SUSPECT_THRESHOLD == 100_000


@pytest.mark.parametrize(
    "amount,quantity,expected",
    [
        (36_000_000, 36, True),  # confirmed cip acza_workbook_unship pattern (~$1M/unit)
        (100_000, 1, False),  # exactly at threshold — not > threshold
        (100_001, 1, True),
        (5_000, 10, False),
        (None, 10, False),
        (5_000, None, False),
        (5_000, 0, False),  # no quantity to divide by — never flagged
        (5_000, -3, False),  # negative quantity — never flagged
        (-36_000_000, 36, True),  # sign-agnostic (abs)
    ],
)
def test_is_unit_price_scale_suspect(amount, quantity, expected: bool) -> None:
    assert is_unit_price_scale_suspect(amount, quantity) is expected


def test_sql_clauses_are_valid_and_mutually_exclusive_shape() -> None:
    suspect = amount_scale_suspect_clause()
    not_suspect = amount_scale_not_suspect_clause()
    # Both must compile into a valid SELECT (SQLAlchemy raises on structural errors).
    assert select(FactInboundShipment.id).where(suspect) is not None
    assert select(FactInboundShipment.id).where(not_suspect) is not None
    assert "quantity" in str(suspect)
    assert "quantity" in str(not_suspect)
