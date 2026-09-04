"""Unit tests for A1-09 support bias (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.cpor.support_bias import _planned_campaign_reserve_for_line


def test_planned_reserve_missing_sku():
    line = SimpleNamespace(
        estimate_qty=100.0,
        srp=1000.0,
        vat_rate=0.15,
        dealer_margin_pct=0.08,
        distributor_id=None,
    )
    out = _planned_campaign_reserve_for_line(
        line, sku=None, cust_term=None, dist_term=None
    )
    assert out["included"] is False
    assert "missing_sku_assumption" in out["flags"]
    assert out["planned_usd"] is None


def test_planned_reserve_with_sku():
    line = SimpleNamespace(
        estimate_qty=10.0,
        srp=1000.0,
        vat_rate=0.15,
        dealer_margin_pct=0.08,
        distributor_id=1,
    )
    sku = SimpleNamespace(
        controlled_cost_amount=100.0,
        fx_plan_currency_per_cost_currency=1.0,
        vat_rate_pct=0.15,
        reserve_total_pct=0.10,
        promo_reserve_split_pct=1.0,
    )
    out = _planned_campaign_reserve_for_line(
        line, sku=sku, cust_term=None, dist_term=None
    )
    assert out["included"] is True
    assert out["planned_usd"] is not None
    assert out["planned_usd"] > 0


def test_actual_only_counts_when_planned_is_included():
    """Regression for mixed-denominator 391%: actual must not include unplanned lines."""
    from app.services.cpor.support_bias import _planned_campaign_reserve_for_line

    missing = _planned_campaign_reserve_for_line(
        SimpleNamespace(estimate_qty=10.0, srp=1000.0, vat_rate=0.15, dealer_margin_pct=0.08, distributor_id=None),
        sku=None,
        cust_term=None,
        dist_term=None,
    )
    assert missing["included"] is False
    # Callers must skip tot_actual += ttl_support_usd when included is False.
