"""CPOR portfolio intelligence (A2-U1) — pure service tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence


def _line(**kwargs):
    defaults = dict(
        product_id=1,
        estimate_qty=10.0,
        result_qty=8.0,
        ttl_support=100.0,
        ttl_support_usd=5.0,
        support_usd=None,
        remark=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_portfolio_usd_and_zar_and_delivery_and_spu(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.cpor.portfolio_intelligence.load_evidence_basis_by_case",
        lambda session, cases, **k: {int(c.id): "none" for c in cases},
    )
    case = SimpleNamespace(
        id=1,
        customer_id=7,
        promotion_type="Sell out PP",
        superseded_by_case_id=None,
        lines=[
            _line(product_id=1, estimate_qty=10, result_qty=8, ttl_support=180.0, ttl_support_usd=10.0),
            _line(product_id=2, estimate_qty=5, result_qty=5, ttl_support=90.0, ttl_support_usd=5.0),
            _line(
                product_id=3,
                estimate_qty=0,
                result_qty=0,
                ttl_support=999.0,
                ttl_support_usd=99.0,
                remark="[voided]",
            ),
        ],
    )
    session = MagicMock()
    scalars = MagicMock()
    scalars.unique.return_value.all.return_value = [case]
    session.scalars.return_value = scalars
    # customer meta then product meta
    session.execute.side_effect = [
        MagicMock(all=MagicMock(return_value=[(7, "C1", "Cust One")])),
        MagicMock(all=MagicMock(return_value=[(1, "NB"), (2, "NB"), (3, "NV")])),
    ]

    out = build_portfolio_intelligence(session)
    assert out["lines_included"] == 2
    assert out["lines_excluded_voided"] == 1
    assert out["totals"]["support_usd"] == 15.0
    assert out["evidence_basis_mix"]["none"] == 1
    assert out["claim_evidenced_only"]["lines_included"] == 0
    assert out["totals"]["support_zar"] == 270.0
    assert abs(out["totals"]["delivery_rate"] - (13 / 15)) < 1e-9
    assert abs(out["totals"]["support_per_unit_sold_usd"] - (15 / 13)) < 1e-9
    assert out["by_bu"][0]["bu"] == "NB"
    assert "claim" not in str(out).lower() or "claim_rate" not in out


def test_empty_portfolio() -> None:
    session = MagicMock()
    scalars = MagicMock()
    scalars.unique.return_value.all.return_value = []
    session.scalars.return_value = scalars
    out = build_portfolio_intelligence(session)
    assert out["cases_in_scope"] == 0
    assert out["totals"]["delivery_rate"] is None
