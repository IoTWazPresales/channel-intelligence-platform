"""Commercial planner program phase 2 routes and services."""

from __future__ import annotations

from app.main import app
from app.services.commercial_planner.intelligence.product_rankings import (
    _score_product,
    _suggested_srp_local,
)
from app.services.commercial_planner.lineup_parse_dispatch import should_parse_lineup_async
from app.services.commercial_planner.lineup_parse_worker import (
    ASYNC_PARSE_BYTE_THRESHOLD,
    ASYNC_PARSE_ROW_THRESHOLD,
)


def test_phase2_routes_registered():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/commercial-planner/lineup-cases/{case_id}/steward-export" in paths
    assert (
        "/api/v1/commercial-planner/plans/{plan_id}/intelligence/customer/{customer_id}/product-rankings/snapshot"
        in paths
    )
    assert "/api/v1/commercial-planner/plans/{plan_id}/intelligence/snapshots" in paths


def test_should_parse_lineup_async_thresholds():
    assert should_parse_lineup_async(file_bytes=b"x" * ASYNC_PARSE_BYTE_THRESHOLD, preview_total_rows=1)
    assert should_parse_lineup_async(file_bytes=b"x", preview_total_rows=ASYNC_PARSE_ROW_THRESHOLD)
    assert not should_parse_lineup_async(file_bytes=b"x", preview_total_rows=10)


def test_score_product_budget_and_buy_plan_signals():
    row = _score_product(
        product_id=1,
        sku="A",
        name="A",
        sellout_avg=10.0,
        forecast_units=None,
        hist_qty=None,
        current_qty=None,
        in_plan=False,
        gp_per_unit=5.0,
        calc_flags=[],
        suggested_srp_local=_suggested_srp_local(lineup_msrp=100.0, net_price=None),
        has_promo_plan=False,
        has_budget_request=True,
        has_buy_plan=True,
    )
    assert row["opportunity_score"] > 10
