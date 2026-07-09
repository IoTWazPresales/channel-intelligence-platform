"""CPOR U2 — recompute path (in-memory objects; no cip)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.recompute import recompute_case_line
from app.services.cpor.waterfall import quantize_money


def _line(**kwargs):
    defaults = dict(
        id=1,
        case_id=10,
        srp=Decimal("13999"),
        vat_rate=Decimal("0.15"),
        dealer_margin_pct=Decimal("0.15"),
        cost_basis=Decimal("9585.07"),
        estimate_qty=Decimal("20"),
        result_qty=None,
        dealer_price=None,
        support_unit=None,
        ttl_support=None,
        support_usd=None,
        ttl_result=None,
        ttl_support_usd=None,
        ttl_result_usd=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_recompute_writes_dealer_and_support():
    session = MagicMock()
    case = SimpleNamespace(id=10, roe_snapshot=Decimal("18.5"), channel="reseller")
    # Use workbook dealer that yields 12297.18 at result 49
    unrounded_support = Decimal("12297.18") / Decimal("49")
    dealer = Decimal("9585.07") - unrounded_support
    # Force inputs via srp path for dealer_price 10347.09 separately —
    # here we set cost/dealer via waterfall from srp; support will differ from workbook row.
    line = _line(result_qty=Decimal("49"))
    rep = recompute_case_line(session, line, case=case)
    from app.services.cpor.waterfall import compute_dealer_price

    expected_dp = float(
        quantize_money(compute_dealer_price("13999", "0.15", "0.15"), "0.0001")
    )
    assert line.dealer_price == expected_dp
    assert line.support_unit is not None
    assert line.ttl_result is not None
    assert line.ttl_support_usd is not None
    assert line.ttl_result_usd is not None
    assert "no_cost_basis" not in rep["flags"]


def test_recompute_no_cost_basis_writes_dealer_only():
    session = MagicMock()
    case = SimpleNamespace(id=10, roe_snapshot=None, channel="reseller")
    line = _line(cost_basis=None, result_qty=Decimal("49"))
    rep = recompute_case_line(session, line, case=case)
    assert line.dealer_price is not None
    assert line.support_unit is None
    assert line.ttl_support is None
    assert line.support_usd is None
    assert line.ttl_result is None
    assert line.ttl_support_usd is None
    assert line.ttl_result_usd is None
    assert "no_cost_basis" in rep["flags"]


def test_recompute_ttl_result_only_when_result_qty():
    session = MagicMock()
    case = SimpleNamespace(id=10, roe_snapshot=Decimal("18"), channel="reseller")
    line = _line(result_qty=None)
    recompute_case_line(session, line, case=case)
    assert line.ttl_result is None
    assert line.ttl_result_usd is None
    assert line.support_unit is not None
    assert line.ttl_support_usd is not None


def test_recompute_missing_roe_null_support_usd():
    session = MagicMock()
    case = SimpleNamespace(id=10, roe_snapshot=None, channel="reseller")
    line = _line()
    rep = recompute_case_line(session, line, case=case)
    assert line.support_usd is None
    assert line.ttl_support_usd is None
    assert line.ttl_result_usd is None
    assert "missing_roe" in rep["flags"]
