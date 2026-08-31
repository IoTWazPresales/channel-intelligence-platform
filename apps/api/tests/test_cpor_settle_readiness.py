"""NS-1a settle readiness facts from existing columns."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.cpor import CporCase, CporCaseLine
from app.services.cpor.pivot import build_case_pivot
from app.services.cpor.settle_readiness import (
    ASSUMPTION_LINE_FLAGS,
    build_settle_readiness,
    case_missing_roe,
    count_open_assumptions_from_line_flags,
    fx_declared,
)


def test_fx_declared_requires_positive_roe():
    case = CporCase(case_code="C26C00001", roe_snapshot=None)
    assert fx_declared(case) is False
    case.roe_snapshot = Decimal("0")
    assert fx_declared(case) is False
    case.roe_snapshot = Decimal("-1.5")
    assert fx_declared(case) is False
    case.roe_snapshot = Decimal("18")
    assert fx_declared(case) is True


def test_case_missing_roe_aligns_with_fx_declared():
    case = CporCase(case_code="C26C00001", roe_snapshot=None)
    assert case_missing_roe(case) is True
    case.roe_snapshot = Decimal("0")
    assert case_missing_roe(case) is True
    case.roe_snapshot = Decimal("-2")
    assert case_missing_roe(case) is True
    case.roe_snapshot = Decimal("18")
    assert case_missing_roe(case) is False


def test_count_open_assumptions_from_line_flags():
    assert count_open_assumptions_from_line_flags(["no_cost_basis", "over_estimate"]) == 1
    assert count_open_assumptions_from_line_flags(["over_estimate"]) == 0
    assert "no_cost_basis" in ASSUMPTION_LINE_FLAGS


def test_build_settle_readiness_shape():
    case = CporCase(case_code="C26C00002", roe_snapshot=Decimal("18.5"))
    out = build_settle_readiness(case, claim_row_count=3, open_assumption_count=1)
    assert out["fx_declared"] is True
    assert out["roe_snapshot"] == 18.5
    assert out["claim_evidence_count"] == 3
    assert out["open_assumption_count"] == 1


def test_line_with_no_cost_basis_counts_as_assumption():
    flags: list[str] = []
    line = CporCaseLine(case_id=1, product_id=1, estimate_qty=1, srp=100, vat_rate=0.15, dealer_margin_pct=0.15)
    if line.cost_basis is None:
        flags.append("no_cost_basis")
    assert count_open_assumptions_from_line_flags(flags) == 1


def _pivot_fixture(roe_snapshot):
    case = SimpleNamespace(id=1, case_code="X", roe_snapshot=roe_snapshot)
    line = SimpleNamespace(
        product_id=1,
        pod_quarter="26Q1",
        support_usd=10.0,
        ttl_support_usd=50.0,
        estimate_qty=5,
        remark=None,
    )
    products = {1: SimpleNamespace(product_line="NB")}
    return case, line, products


@pytest.mark.parametrize("roe_snapshot", [None, Decimal("0"), Decimal("-1.5")])
def test_pivot_missing_roe_when_roe_not_positive(roe_snapshot):
    case, line, products = _pivot_fixture(roe_snapshot)
    pivot = build_case_pivot(MagicMock(), case, [line], products)
    assert pivot["missing_roe"] is True
    assert pivot["grand_total_usd"] == 50.0


def test_pivot_missing_roe_false_when_roe_positive():
    case, line, products = _pivot_fixture(Decimal("18.5"))
    pivot = build_case_pivot(MagicMock(), case, [line], products)
    assert pivot["missing_roe"] is False
