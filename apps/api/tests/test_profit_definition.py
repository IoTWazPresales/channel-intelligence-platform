"""N-0080: one profit definition shared by lineup profitability, planner lines and CPOR margin."""

from __future__ import annotations

import pytest

from app.services.commercial_planner.calculator import CommercialCalcInputs, compute_line_economics
from app.services.commercial_planner.lineup_pricing import LineupPricingInputs, compute_lineup_pricing
from app.services.profit_definition import HEADLINE_COST_BASIS, compute_profit, profit_payload


def test_margin_is_dap_minus_pm_controlled_cost_and_landed_is_never_subtracted():
    with_landed = compute_profit(dap_per_unit=100.0, pm_controlled_cost=70.0, landed_cost=85.0, units=10)
    without_landed = compute_profit(dap_per_unit=100.0, pm_controlled_cost=70.0, units=10)
    assert with_landed.margin_per_unit == pytest.approx(30.0)
    assert with_landed.margin_total == pytest.approx(300.0)
    assert with_landed.margin_pct == pytest.approx(0.3)
    assert with_landed.landed_cost_per_unit == pytest.approx(85.0)
    assert with_landed.margin_total == without_landed.margin_total
    assert "landed_cost_not_recorded" in without_landed.flags
    assert "landed_cost_not_recorded" not in with_landed.flags


def test_support_is_deducted_and_missing_inputs_are_flagged_not_zeroed():
    fig = compute_profit(dap_per_unit=100.0, pm_controlled_cost=70.0, units=4, support_per_unit=40.0)
    assert fig.margin_per_unit == pytest.approx(-10.0)
    assert "negative_margin" in fig.flags

    no_cost = compute_profit(dap_per_unit=100.0, pm_controlled_cost=None, units=4)
    assert no_cost.margin_per_unit is None and no_cost.margin_total is None
    assert "missing_pm_controlled_cost" in no_cost.flags

    no_units = compute_profit(dap_per_unit=100.0, pm_controlled_cost=70.0, units=None)
    assert no_units.margin_per_unit == pytest.approx(30.0) and no_units.margin_total is None
    assert "missing_quantity" in no_units.flags


def test_payload_names_every_figure_and_its_cost_basis():
    p = profit_payload(compute_profit(dap_per_unit=100.0, pm_controlled_cost=70.0, landed_cost=85.0, units=1))
    assert p["cost_basis"] == HEADLINE_COST_BASIS == "pm_controlled_cost"
    assert p["cost_basis_label"] == "PM controlled cost"
    assert p["labels"]["margin"] == "Margin vs PM controlled cost"
    assert "not in margin" in p["labels"]["landed_cost"]
    for key in ("dap_per_unit", "pm_controlled_cost_per_unit", "landed_cost_per_unit", "margin_per_unit"):
        assert key in p


def test_lineup_pricing_profit_reads_the_definition_unchanged():
    res = compute_lineup_pricing(
        LineupPricingInputs(
            srp_inc_vat_local=11500.0,
            vat_rate_pct=0.15,
            dealer_margin_pct=0.12,
            rebate_pct=0.03,
            distributor_margin_pct=0.08,
            import_tax_pct=0.0,
            roe_local_per_cost_currency=18.0,
            controlled_cost_amount=300.0,
            quantity_units=10,
        )
    )
    expected = compute_profit(dap_per_unit=res.calc_dap_cost_currency, pm_controlled_cost=300.0, units=10)
    assert res.calc_profit_per_unit == pytest.approx(expected.margin_per_unit, abs=1e-3)
    assert res.calc_profit_total == pytest.approx(expected.margin_total, abs=1e-2)


def test_planner_margin_is_measured_from_sell_in_dap_not_distributor_net():
    res = compute_line_economics(
        CommercialCalcInputs(
            target_units=100,
            target_srp_local=1150,
            promo_srp_local=None,
            promo_mix_pct=0.0,
            fx_plan_currency_per_cost_currency=1.0,
            vat_rate_pct=0.15,
            controlled_cost_amount=600,
            customer_margin_pct=0.12,
            customer_rebate_pct=0.03,
            distributor_margin_pct=0.08,
            reserve_total_pct=0.0,
            promo_reserve_split_pct=0.5,
        )
    )
    # ex-VAT 1000; channel stack 23% -> sell-in (DAP) 770. Margin = 770 - 600 = 170 per unit.
    assert res.calc_oem_sell_in_amount == pytest.approx(770.0)
    assert res.calc_internal_gp_amount == pytest.approx(170.0 * 100)
    assert res.calc_distributor_net_amount == pytest.approx(770.0 * 0.92)
    assert "Margin vs PM controlled cost" in res.explanation
