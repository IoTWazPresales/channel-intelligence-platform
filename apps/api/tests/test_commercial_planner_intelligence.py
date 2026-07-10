"""Commercial planner intelligence and lineup preview."""

from __future__ import annotations

from app.core.feature_flags import commercial_planner_enabled
from app.main import app
from app.services.commercial_planner.lineup_case_parser import _parse_file_to_row_dicts
from app.services.commercial_planner.intelligence.product_rankings import (
    _score_product,
    _suggested_srp_local,
)


def test_commercial_planner_feature_flag_default_on():
    assert commercial_planner_enabled() is True


def test_score_product_respects_already_in_plan():
    row = _score_product(
        product_id=1,
        sku="SKU-A",
        name="Product A",
        sellout_avg=100.0,
        forecast_units=120.0,
        hist_qty=50.0,
        current_qty=None,
        in_plan=True,
        gp_per_unit=10.0,
        calc_flags=[],
        suggested_srp_local=1000.0,
        has_promo_plan=False,
        has_budget_request=False,
        has_buy_plan=False,
    )
    assert row["already_in_plan"] is True
    assert row["opportunity_score"] < 80
    assert row["suggested_srp_local"] == 1000.0


def test_suggested_srp_prefers_lineup_msrp():
    assert _suggested_srp_local(lineup_msrp=1500.0, net_price=800.0) == 1500.0


def test_suggested_srp_anchors_to_net_price():
    assert _suggested_srp_local(lineup_msrp=None, net_price=500.0) == 560.0


def test_parse_file_to_row_dicts_csv_minimal():
    csv = b"sku,qty,msrp\nTEST-SKU,10,999\n"
    rows, warnings, total, resolved, unresolved, _uc, _ud, _cols = _parse_file_to_row_dicts(
        "test.csv",
        csv,
        product_map={},
        customer_map={},
        distributor_map={},
    )
    assert total == 1
    assert unresolved == 1
    assert rows[0]["sku_raw"] == "TEST-SKU"


def test_parse_file_drops_currency_margin_columns_mapped_as_pct():
    """Workbooks label dealer margin / rebate as currency amounts — must not overflow Numeric(8,4)."""
    csv = (
        b"part number,SRP,Dealer margin,Rebate,Disti margin,VAT,Qty\n"
        b"90PF0561-M00WY0,94999,74347.04,72860.10,67585.03,0.1,0.15\n"
    )
    rows, _warnings, total, _resolved, _unresolved, _uc, _ud, _cols = _parse_file_to_row_dicts(
        "lineup.csv",
        csv,
        product_map={},
        customer_map={},
        distributor_map={},
    )
    assert total == 1
    row = rows[0]
    assert row["rebate_pct_evidence"] is None
    assert row["dealer_margin_pct_evidence"] is None
    assert row["distributor_margin_pct_evidence"] is None
    assert row["vat_pct_evidence"] == 0.1
    assert "pct_evidence_out_of_range" in row["diagnostic_codes"]


def test_product_rankings_route_registered():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/commercial-planner/plans/{plan_id}/intelligence/customer/{customer_id}/product-rankings" in paths
