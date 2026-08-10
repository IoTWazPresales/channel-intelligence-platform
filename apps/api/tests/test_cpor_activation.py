"""CPOR activation vs listing price (BACKLOG-130) — no_case / not_activated / consistent."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.listing_capture.cpor_activation import evaluate_cpor_activation


def _listing(*, customer_id: int = 10, product_id: int | None = 100) -> SimpleNamespace:
    return SimpleNamespace(customer_id=customer_id, product_id=product_id)


def test_no_product_link() -> None:
    out = evaluate_cpor_activation(MagicMock(), _listing(product_id=None), listing_price=999.0)
    assert out["status"] == "no_product_link"


def test_no_price() -> None:
    out = evaluate_cpor_activation(MagicMock(), _listing(), listing_price=None)
    assert out["status"] == "no_price"


def test_no_case_detected() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    out = evaluate_cpor_activation(session, _listing(), listing_price=1200.0, as_of=date(2026, 8, 10))
    assert out["status"] == "no_case_detected"
    assert "No CPOR case detected" in out["message"]


def test_not_activated_when_listing_higher() -> None:
    case = SimpleNamespace(
        id=5,
        case_code="CPOR-1",
        status="open",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )
    line = SimpleNamespace(id=50, srp=1000.0)
    session = MagicMock()
    session.execute.return_value.all.return_value = [(case, line)]
    out = evaluate_cpor_activation(session, _listing(), listing_price=1500.0, as_of=date(2026, 8, 10))
    assert out["status"] == "not_activated"
    assert out["case_price"] == 1000.0
    assert out["case_id"] == 5


def test_price_consistent_at_or_below() -> None:
    case = SimpleNamespace(
        id=5,
        case_code="CPOR-1",
        status="open",
        window_start=date.today() - timedelta(days=1),
        window_end=date.today() + timedelta(days=1),
    )
    line = SimpleNamespace(id=50, srp=1000.0)
    session = MagicMock()
    session.execute.return_value.all.return_value = [(case, line)]
    out = evaluate_cpor_activation(session, _listing(), listing_price=999.0)
    assert out["status"] == "price_consistent"


def test_excluded_status_treated_as_no_case() -> None:
    case = SimpleNamespace(
        id=5,
        case_code="CPOR-X",
        status="cancelled",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )
    line = SimpleNamespace(id=50, srp=1000.0)
    session = MagicMock()
    session.execute.return_value.all.return_value = [(case, line)]
    out = evaluate_cpor_activation(session, _listing(), listing_price=900.0, as_of=date(2026, 8, 10))
    assert out["status"] == "no_case_detected"
