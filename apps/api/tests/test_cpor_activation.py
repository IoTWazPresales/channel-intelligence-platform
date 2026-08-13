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


def test_promo_preferred_over_sell_out() -> None:
    promo = SimpleNamespace(
        id=10,
        case_code="ST-1",
        status="open",
        origin="native",
        promotion_type="Sell-Through PP",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )
    sell_out = SimpleNamespace(
        id=11,
        case_code="SO-1",
        status="open",
        origin="native",
        promotion_type="Sell out PP",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        (promo, SimpleNamespace(id=1, srp=7999.0)),
        (sell_out, SimpleNamespace(id=2, srp=14999.0)),
    ]
    out = evaluate_cpor_activation(session, _listing(), listing_price=10999.0, as_of=date(2026, 8, 13))
    assert out["status"] == "not_activated"
    assert out["case_code"] == "ST-1"
    assert out["case_price"] == 7999.0
    assert out["price_basis"] == "promo"


def test_sell_out_only_when_no_promo() -> None:
    sell_out = SimpleNamespace(
        id=11,
        case_code="SO-1",
        status="open",
        origin="native",
        promotion_type="Sell out PP",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )
    session = MagicMock()
    session.execute.return_value.all.return_value = [(sell_out, SimpleNamespace(id=2, srp=14999.0))]
    out = evaluate_cpor_activation(session, _listing(), listing_price=10999.0, as_of=date(2026, 8, 13))
    assert out["status"] == "price_consistent"
    assert out["case_code"] == "SO-1"
    assert out["price_basis"] == "sell_out"


def test_historical_fnb_day_not_applied_outside_line_window() -> None:
    promo = SimpleNamespace(
        id=310,
        case_code="C26759823",
        status="ended",
        origin="historical_import",
        promotion_type="Sell-Through PP",
        window_start=date(2026, 8, 3),
        window_end=date(2026, 8, 31),
    )
    sell_out = SimpleNamespace(
        id=311,
        case_code="C26760971",
        status="ended",
        origin="historical_import",
        promotion_type="Sell out PP",
        window_start=date(2026, 7, 30),
        window_end=date(2026, 8, 31),
    )
    fnb = SimpleNamespace(
        import_job_id=978,
        case_code="C26759823",
        promotion_type="Sell-Through PP",
        window_start=date(2026, 8, 15),
        window_end=date(2026, 8, 15),
        srp=9999.0,
        lifecycle_status="ended",
        resolved_product_id=100,
    )
    standing = SimpleNamespace(
        import_job_id=978,
        case_code="C26759823",
        promotion_type="Sell-Through PP",
        window_start=date(2026, 8, 3),
        window_end=date(2026, 8, 9),
        srp=10999.0,
        lifecycle_status="ended",
        resolved_product_id=100,
    )
    so_line = SimpleNamespace(
        import_job_id=978,
        case_code="C26760971",
        promotion_type="Sell out PP",
        window_start=date(2026, 7, 30),
        window_end=date(2026, 8, 31),
        srp=14999.0,
        lifecycle_status="ended",
        resolved_product_id=100,
    )
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        (promo, SimpleNamespace(id=2937, srp=9999.0)),
        (sell_out, SimpleNamespace(id=2968, srp=14999.0)),
    ]
    session.scalars.return_value.all.return_value = [fnb, standing, so_line]
    out = evaluate_cpor_activation(session, _listing(), listing_price=10999.0, as_of=date(2026, 8, 13))
    assert out["status"] == "price_consistent"
    assert out["case_code"] == "C26760971"
    assert out["case_price"] == 14999.0
    assert out["price_basis"] == "sell_out"


def test_historical_promo_line_window_covers_as_of() -> None:
    promo = SimpleNamespace(
        id=310,
        case_code="C26759823",
        status="ended",
        origin="historical_import",
        promotion_type="Sell-Through PP",
        window_start=date(2026, 8, 3),
        window_end=date(2026, 8, 31),
    )
    stg = SimpleNamespace(
        import_job_id=978,
        case_code="C26759823",
        promotion_type="Sell-Through PP",
        window_start=date(2026, 8, 10),
        window_end=date(2026, 8, 16),
        srp=7999.0,
        lifecycle_status="ended",
        resolved_product_id=100,
    )
    session = MagicMock()
    session.execute.return_value.all.return_value = [(promo, SimpleNamespace(id=1, srp=7999.0))]
    session.scalars.return_value.all.return_value = [stg]
    out = evaluate_cpor_activation(session, _listing(), listing_price=11369.0, as_of=date(2026, 8, 13))
    assert out["status"] == "not_activated"
    assert out["case_price"] == 7999.0
    assert out["price_basis"] == "promo"
    assert out["line_window_start"] == "2026-08-10"
    assert out["line_window_end"] == "2026-08-16"
