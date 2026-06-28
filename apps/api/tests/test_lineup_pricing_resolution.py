"""Unit tests for lineup pricing resolution (file evidence vs trade-term fallbacks)."""

import math

from app.services.commercial_planner.lineup_pricing_resolution import (
    LineupTradeTermDefaults,
    resolve_lineup_pricing,
)


def _close(a, b, tol=1e-6):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def test_file_value_overrides_trade_term():
    """File dealer margin (as percent) wins over the customer-term default."""
    defaults = LineupTradeTermDefaults(dealer_margin_pct=0.12, rebate_pct=0.03)
    res = resolve_lineup_pricing(
        srp_inc_vat_local=1000.0,
        quantity_units=10,
        file_dealer_margin_pct=20.0,  # 20% entered as whole number
        defaults=defaults,
    )
    assert res.pricing_chain["sources"]["dealer_margin_pct"] == "file"
    assert _close(res.pricing_chain["inputs"]["dealer_margin_pct"], 0.20)
    # rebate fell back to the trade term
    assert res.pricing_chain["sources"]["rebate_pct"] == "trade_term"
    assert _close(res.pricing_chain["inputs"]["rebate_pct"], 0.03)


def test_percent_normalisation_only_for_pct_fields_not_roe():
    res = resolve_lineup_pricing(
        srp_inc_vat_local=1150.0,
        quantity_units=1,
        file_vat_pct=15.0,
        file_roe=18.5,  # ROE must NOT be divided by 100
        defaults=LineupTradeTermDefaults(controlled_cost_amount=10.0),
    )
    assert _close(res.pricing_chain["inputs"]["vat_rate_pct"], 0.15)
    assert _close(res.pricing_chain["inputs"]["roe_local_per_cost_currency"], 18.5)


def test_import_tax_divides_disti_cost_before_roe():
    """import tax 45% : pre_dap = disti_cost / 1.45, then / ROE (matches workbook convention)."""
    # No margins/rebate/vat so disti_cost == srp; isolates the import-tax + ROE steps.
    res = resolve_lineup_pricing(
        srp_inc_vat_local=1450.0,
        quantity_units=1,
        file_vat_pct=0.0,
        file_dealer_margin_pct=0.0,
        file_rebate_pct=0.0,
        file_distributor_margin_pct=0.0,
        file_import_tax_pct=45.0,
        file_roe=10.0,
        defaults=LineupTradeTermDefaults(controlled_cost_amount=50.0),
    )
    out = res.pricing_chain["outputs"]
    assert _close(out["calc_disti_cost_local"], 1450.0)
    assert _close(out["calc_pre_dap_local"], 1000.0)  # 1450 / 1.45
    assert _close(out["calc_dap_cost_currency"], 100.0)  # 1000 / 10
    assert _close(out["calc_profit_per_unit"], 50.0)  # 100 - 50 PM bottom


def test_missing_pm_bottom_flag_without_blocking():
    res = resolve_lineup_pricing(
        srp_inc_vat_local=1000.0,
        quantity_units=5,
        file_vat_pct=0.0,
        file_dealer_margin_pct=0.0,
        file_rebate_pct=0.0,
        file_distributor_margin_pct=0.0,
        file_roe=1.0,
        defaults=LineupTradeTermDefaults(controlled_cost_amount=None),
    )
    assert "missing_pm_bottom" in res.flags
    assert res.pricing_chain["sources"]["controlled_cost_amount"] == "missing"
    # DAP is still computable even without PM bottom
    assert _close(res.pricing_chain["outputs"]["calc_dap_cost_currency"], 1000.0)
    assert res.pricing_chain["outputs"]["calc_profit_total"] is None


def test_evidence_columns_preserved_in_chain():
    res = resolve_lineup_pricing(
        srp_inc_vat_local=1000.0,
        quantity_units=1,
        file_roe=1.0,
        defaults=LineupTradeTermDefaults(controlled_cost_amount=10.0),
        evidence={"actual_dap_evidence_local": 123.45, "old_srp_local": 900.0, "net_price_evidence_local": None},
    )
    ev = res.pricing_chain["evidence"]
    assert ev["actual_dap_evidence_local"] == 123.45
    assert ev["old_srp_local"] == 900.0
    assert "net_price_evidence_local" not in ev  # None dropped
