import pytest

from app.services.commercial_planner.calculator import CommercialCalcInputs, compute_line_economics
from app.services.commercial_planner.suggestions import SuggestionInputs, build_pricing_suggestion, build_promo_mix_suggestion, build_quantity_suggestion


def test_commercial_calculator_outputs_reserves_and_gp():
    result = compute_line_economics(
        CommercialCalcInputs(
            target_units=100,
            target_srp_local=1200,
            promo_srp_local=1000,
            promo_mix_pct=0.5,
            fx_rate_to_usd=20,
            vat_rate_pct=0.15,
            landed_cost_usd=30,
            customer_margin_pct=0.12,
            customer_rebate_pct=0.03,
            distributor_margin_pct=0.08,
            reserve_total_pct=0.10,
            promo_reserve_split_pct=0.5,
        )
    )
    assert result.sell_in_price_usd > 0
    assert result.promo_reserve_usd > 0
    assert result.non_promo_reserve_usd > 0
    assert isinstance(result.flags, list)


def test_commercial_calculator_still_runs_with_placeholder_defaults_but_flags_issues():
    """Mirrors planner behavior when terms rows are missing: calculator uses fallbacks and surfaces economics issues."""
    result = compute_line_economics(
        CommercialCalcInputs(
            target_units=100,
            target_srp_local=1200,
            promo_srp_local=None,
            promo_mix_pct=0.5,
            fx_rate_to_usd=1.0,
            vat_rate_pct=0.15,
            landed_cost_usd=0.0,
            customer_margin_pct=0.0,
            customer_rebate_pct=0.0,
            distributor_margin_pct=0.0,
            reserve_total_pct=0.10,
            promo_reserve_split_pct=0.5,
        )
    )
    assert "missing_or_invalid_landed_cost" in result.flags


def test_commercial_calculator_flags_impossible_stack():
    result = compute_line_economics(
        CommercialCalcInputs(
            target_units=50,
            target_srp_local=800,
            promo_srp_local=None,
            promo_mix_pct=0.5,
            fx_rate_to_usd=18,
            vat_rate_pct=0.15,
            landed_cost_usd=100,
            customer_margin_pct=0.5,
            customer_rebate_pct=0.3,
            distributor_margin_pct=0.2,
            reserve_total_pct=0.1,
            promo_reserve_split_pct=0.5,
        )
    )
    assert "impossible_margin_stack" in result.flags


def test_suggestion_builders_return_explainable_payloads():
    inp = SuggestionInputs(
        avg_sellout_units=100,
        prior_planned_units=95,
        forecast_units=120,
        latest_net_price=850,
        target_srp_local=1000,
        promo_mix_pct=0.5,
    )
    qty, qty_reason, qty_conf = build_quantity_suggestion(inp)
    target, promo, price_reason, price_conf = build_pricing_suggestion(inp)
    mix, mix_reason, mix_conf = build_promo_mix_suggestion(inp)
    assert qty > 0
    assert qty_reason
    assert qty_conf in {"low", "medium", "high"}
    assert target >= promo
    assert price_reason
    assert price_conf in {"low", "medium", "high"}
    assert 0 <= mix <= 1
    assert mix_reason
    assert mix_conf in {"low", "medium", "high"}


def test_pricing_suggestion_uses_lineup_msrp_as_fallback_anchor():
    """When no net-price data is available, lineup MSRP/list anchors the pricing suggestion."""
    inp = SuggestionInputs(
        avg_sellout_units=0,
        prior_planned_units=None,
        forecast_units=None,
        latest_net_price=None,
        target_srp_local=900,
        promo_mix_pct=0.5,
        lineup_msrp_local=1100.0,
        lineup_promo_price_local=950.0,
        lineup_period_label="2026-Q2",
        lineup_job_id=10,
    )
    target, promo, reason, confidence = build_pricing_suggestion(inp)
    assert target == 1100.0, "Should use lineup MSRP as price anchor"
    assert promo == 950.0, "Should use lineup promo price when available"
    assert "lineup MSRP" in reason
    assert "2026-Q2" in reason
    assert confidence == "medium"


def test_quantity_suggestion_includes_lineup_units_as_baseline():
    """Lineup quantity from historical import is used as a baseline when higher than sellout."""
    inp = SuggestionInputs(
        avg_sellout_units=50,
        prior_planned_units=None,
        forecast_units=None,
        latest_net_price=None,
        target_srp_local=1000,
        promo_mix_pct=0.5,
        lineup_quantity_units=200.0,
        lineup_job_id=10,
    )
    qty, reason, confidence = build_quantity_suggestion(inp)
    # Base = max(50, 200) * 1.08 = 216
    assert qty == pytest.approx(216.0, abs=0.1)
    assert "lineup qty" in reason
