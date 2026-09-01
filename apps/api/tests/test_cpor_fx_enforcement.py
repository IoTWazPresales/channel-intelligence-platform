"""NS-1b FX mode + blocked-settle enforcement."""

from __future__ import annotations

from decimal import Decimal

from app.models.cpor import CporCase
from app.services.cpor.settle_readiness import (
    build_fx_basis_line,
    build_settle_readiness,
    settle_fx_blocked,
)


def test_settle_fx_blocked_without_mode():
    case = CporCase(case_code="X", roe_snapshot=Decimal("18.5"), fx_mode=None)
    assert settle_fx_blocked(case) is True


def test_settle_allowed_with_booked_mode():
    case = CporCase(case_code="X", roe_snapshot=Decimal("18.5"), fx_mode="booked")
    assert settle_fx_blocked(case) is False
    line = build_fx_basis_line(case)
    assert line is not None
    assert "booked" in line


def test_settle_readiness_includes_fx_basis():
    case = CporCase(case_code="X", roe_snapshot=Decimal("18"), fx_mode="floating")
    out = build_settle_readiness(case, claim_row_count=2, open_assumption_count=0)
    assert out["fx_settle_allowed"] is True
    assert out["fx_basis_line"] is not None
    assert "floating" in out["fx_basis_line"]
