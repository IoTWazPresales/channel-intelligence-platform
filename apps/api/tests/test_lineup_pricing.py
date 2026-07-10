"""Unit 1 (Session B) — backwards lineup pricing, validated against the ACZA lineup workbook."""

from __future__ import annotations

import pytest

from app.services.commercial_planner.lineup_pricing import (
    LineupPricingInputs,
    compute_lineup_pricing,
)


def _nb_inputs(srp: float, controlled_cost: float | None = None, qty: float | None = None) -> LineupPricingInputs:
    # ACZA NB / ZA trade terms observed in the workbook.
    return LineupPricingInputs(
        srp_inc_vat_local=srp,
        vat_rate_pct=0.15,
        dealer_margin_pct=0.08,
        rebate_pct=0.06,
        distributor_margin_pct=0.0724,
        import_tax_pct=0.0,
        roe_local_per_cost_currency=17.73,
        controlled_cost_amount=controlled_cost,
        quantity_units=qty,
    )


def test_workbook_row_ux8406_to_the_cent():
    # UX8406CA: New SRP 37999 -> file DAP 1495.002822605753
    r = compute_lineup_pricing(_nb_inputs(37999))
    assert r.calc_dealer_price_local == pytest.approx(30399.2, abs=0.01)
    assert r.calc_net_price_local == pytest.approx(28575.248, abs=0.01)
    assert r.calc_disti_cost_local == pytest.approx(26506.4000448, abs=0.01)
    assert r.calc_dap_cost_currency == pytest.approx(1495.0028, abs=0.001)


def test_workbook_row_v3607_to_the_cent():
    # V3607VU: New SRP 20999 -> file DAP 826.1681694754652
    r = compute_lineup_pricing(_nb_inputs(20999))
    assert r.calc_dealer_price_local == pytest.approx(16799.2, abs=0.01)
    assert r.calc_net_price_local == pytest.approx(15791.248, abs=0.01)
    assert r.calc_disti_cost_local == pytest.approx(14647.9616448, abs=0.01)
    assert r.calc_dap_cost_currency == pytest.approx(826.1682, abs=0.001)


def test_import_tax_45pct_divides_disti_cost_then_roe():
    # Warren: import tax e.g. 45% -> disti_cost / 1.45 then / ROE.
    base = _nb_inputs(37999)
    taxed = LineupPricingInputs(
        srp_inc_vat_local=base.srp_inc_vat_local,
        vat_rate_pct=base.vat_rate_pct,
        dealer_margin_pct=base.dealer_margin_pct,
        rebate_pct=base.rebate_pct,
        distributor_margin_pct=base.distributor_margin_pct,
        import_tax_pct=0.45,
        roe_local_per_cost_currency=base.roe_local_per_cost_currency,
        controlled_cost_amount=None,
        quantity_units=None,
    )
    r = compute_lineup_pricing(taxed)
    expected_dap = (26506.4000448 / 1.45) / 17.73
    assert r.calc_dap_cost_currency == pytest.approx(expected_dap, abs=0.001)
    assert r.calc_pre_dap_local == pytest.approx(26506.4000448 / 1.45, abs=0.01)


def test_missing_pm_bottom_flags_not_blocks():
    r = compute_lineup_pricing(_nb_inputs(37999, controlled_cost=None))
    assert "missing_pm_bottom" in r.flags
    assert r.calc_profit_per_unit is None
    # DAP still computed despite missing PM bottom.
    assert r.calc_dap_cost_currency > 0


def test_profit_when_pm_bottom_present():
    r = compute_lineup_pricing(_nb_inputs(37999, controlled_cost=1200.0, qty=14))
    assert "missing_pm_bottom" not in r.flags
    assert r.calc_profit_per_unit == pytest.approx(1495.0028 - 1200.0, abs=0.01)
    assert r.calc_profit_total == pytest.approx((1495.0028 - 1200.0) * 14, abs=0.5)


def test_rebate_override_changes_dap():
    base = compute_lineup_pricing(_nb_inputs(37999))
    higher_rebate = LineupPricingInputs(
        srp_inc_vat_local=37999,
        vat_rate_pct=0.15,
        dealer_margin_pct=0.08,
        rebate_pct=0.12,
        distributor_margin_pct=0.0724,
        import_tax_pct=0.0,
        roe_local_per_cost_currency=17.73,
        controlled_cost_amount=None,
        quantity_units=None,
    )
    r = compute_lineup_pricing(higher_rebate)
    # More rebate -> lower net -> lower DAP.
    assert r.calc_dap_cost_currency < base.calc_dap_cost_currency


def test_missing_srp_does_not_crash():
    r = compute_lineup_pricing(_nb_inputs(0))
    assert "missing_or_invalid_srp" in r.flags
    assert r.calc_dap_cost_currency == 0.0
    assert r.calc_profit_per_unit is None
