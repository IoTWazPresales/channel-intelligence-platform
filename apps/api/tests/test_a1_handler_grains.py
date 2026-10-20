"""Plan-vs-executed query rows match the requested grain (audit 2026-10-20)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.query.handlers.a1_pve import handle_a1
from app.query.types import QueryRequest

SC = {"fill_rate": 0.8, "line_hit_rate": 0.5, "deal_stock_units": 30, "over_plan_intake_units": 30, "planned_units": 300,
      "short_exposure_units": 12, "unplanned_intake_units": 4, "pipeline_units_in_plan": 7,
      "no_po_blind_spot": {"line_count": 3, "planned_units": 40, "planned_value_plan": 1000}}
PAYLOAD = {
    "period_range": {"from": "26Q2", "to": "26Q3"},
    "scorecard": SC,
    "scorecard_by_bu": {"NB": {**SC, "fill_rate": 0.9}, "NR": {**SC, "fill_rate": 0.6}},
    "trend": [{"period_label": "26Q2", "fill_rate": 0.7, "deal_stock_units": 10}, {"period_label": "26Q3", "fill_rate": 0.9, "deal_stock_units": 20}],
    "volume_bias": {"by_bu": [{"bu": "NB", "line_count": 3, "mean_signed_bias": 0.2}, {"bu": "NR", "line_count": 1, "mean_signed_bias": -0.2}]},
    "drill_rows": [],
}


async def _run(metric, grains):
    with patch("app.query.handlers.a1_pve.plan_vs_executed_read_model", new_callable=AsyncMock, return_value=PAYLOAD):
        return await handle_a1(AsyncMock(), QueryRequest(metric=metric, grains=grains), metric_key=metric)


@pytest.mark.anyio
async def test_period_grain_returns_one_point_per_quarter():
    hr = await _run("fill_rate", ["period"])
    assert hr.series == [{"bucket_key": "26Q2", "value": 0.7}, {"bucket_key": "26Q3", "value": 0.9}]
    assert hr.value == 0.8


@pytest.mark.anyio
async def test_period_bu_grain_returns_the_metric_per_product_line():
    hr = await _run("fill_rate", ["period", "bu"])
    assert [(r["bu"], r["value"]) for r in hr.rows] == [("NB", 0.9), ("NR", 0.6)]


@pytest.mark.anyio
async def test_volume_bias_values_and_weighted_total():
    hr = await _run("volume_bias", ["bu"])
    assert [r["value"] for r in hr.rows] == [0.2, -0.2]
    assert hr.value == pytest.approx((0.2 * 3 - 0.2) / 4)


@pytest.mark.anyio
async def test_over_plan_intake_is_units_and_no_po_is_a_count():
    assert (await _run("over_plan_intake_rate", ["period"])).value == 30
    assert (await _run("no_po_blind_spot", ["period"])).value == 3
