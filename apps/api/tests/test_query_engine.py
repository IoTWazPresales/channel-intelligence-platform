"""P3-2 query engine unit tests — validation gate, invariants, cache, not_implemented."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.query.cache import clear_query_cache, get_cached, set_cached, cache_key
from app.query.engine import execute_query
from app.query.handlers import A1_KEYS, A2_KEYS, A3_KEYS, handler_name_for
from app.query.types import HandlerResult, QueryRequest
from app.semantics.registry import validate_metric_grain


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_query_cache()
    yield
    clear_query_cache()


def test_handler_registry_covers_v1_set():
    assert handler_name_for("channel_stock") == "a3_stock"
    assert handler_name_for("fill_rate") == "a1_pve"
    assert handler_name_for("support_spend") == "a2_cpor"
    assert handler_name_for("sellout_units") == "volume_series"
    assert handler_name_for("cst_sellthrough_units") == "volume_series"
    assert handler_name_for("forecast_units") is None
    assert "weeks_of_cover" in A3_KEYS
    assert "volume_bias" in A1_KEYS
    assert "delivery_rate" in A2_KEYS


@pytest.mark.anyio
async def test_execute_refuses_invalid_grain():
    db = AsyncMock()
    result = await execute_query(
        db,
        metric="weeks_of_cover",
        grains=["period", "bu"],
        tenant_id="default",
    )
    assert result.status == "refused"
    assert result.ok is False
    assert "distributor" in (result.message or "").lower() or "not allowed" in (
        result.message or ""
    ).lower()
    db.execute.assert_not_called()


@pytest.mark.anyio
async def test_execute_refuses_claim_rate():
    db = AsyncMock()
    result = await execute_query(
        db,
        metric="claim_rate",
        grains=["customer"],
        tenant_id="default",
    )
    assert result.status == "refused"
    assert result.ok is False


@pytest.mark.anyio
async def test_explain_a3_no_db():
    db = AsyncMock()
    result = await execute_query(
        db,
        metric="channel_stock",
        grains=["distributor", "product"],
        explain_only=True,
    )
    assert result.status == "ok"
    assert result.handler == "a3_stock"
    assert "latest_per_distributor_product_soh" in result.invariants_applied
    assert result.explain is not None
    db.execute.assert_not_called()


@pytest.mark.anyio
async def test_not_implemented_metric_after_valid_grain():
    db = AsyncMock()
    # forecast_units allows period grain
    result = await execute_query(
        db,
        metric="forecast_units",
        grains=["period"],
        tenant_id="default",
    )
    assert result.status == "not_implemented"
    assert result.ok is False
    assert result.handler == "not_implemented"


@pytest.mark.anyio
async def test_a3_handler_invariants_and_value():
    from app.query.handlers import a3_stock

    db = AsyncMock()
    stock = {(1, 10): 100.0, (1, 20): 50.0}
    vel = {(1, 10): 10.0, (1, 20): 5.0}

    with (
        patch(
            "app.query.handlers.a3_stock.derived_stock_by_dist_product",
            new_callable=AsyncMock,
            return_value=stock,
        ),
        patch(
            "app.query.handlers.a3_stock.sellout_velocity_52wk_by_dist_product",
            new_callable=AsyncMock,
            return_value=vel,
        ),
    ):
        req = QueryRequest(
            metric="weeks_of_cover",
            grains=["distributor", "product"],
            tenant_id="default",
            filters={"woc_source": "live"},
        )
        hr = await a3_stock.handle_a3(db, req, metric_key="weeks_of_cover")
    assert hr.status == "ok"
    assert "latest_per_distributor_product_soh" in hr.invariants_applied
    assert "pipeline_never_counts" in hr.invariants_applied
    # portfolio WoC = 150 / 15 = 10
    assert hr.value == pytest.approx(10.0)
    assert len(hr.rows or []) == 2


@pytest.mark.anyio
async def test_a3_handler_default_reads_observations() -> None:
    from datetime import date

    from app.query.handlers import a3_stock
    from app.services.woc_observation_read import WocObservationRow

    db = AsyncMock()
    obs = [
        WocObservationRow(
            distributor_id=1,
            product_id=10,
            snapshot_date=date(2026, 8, 10),
            cover_as_of_date=date(2026, 8, 17),
            reported_soh=100,
            sell_out_since=0,
            landed_since=0,
            derived_stock=100,
            weekly_velocity=10.0,
            weeks_of_cover=10.0,
            replenishment_flag=False,
            replenishment_threshold_weeks=4.0,
            trigger="dsi_apply",
            formula_version="A3-02.v1",
            params={},
            data_vintage={},
            import_job_id=12,
        )
    ]
    with (
        patch(
            "app.query.handlers.a3_stock.latest_woc_observations",
            new_callable=AsyncMock,
            return_value=obs,
        ),
        patch(
            "app.query.handlers.a3_stock.derived_stock_by_dist_product",
            new_callable=AsyncMock,
            return_value={(1, 10): 999.0},
        ) as live,
    ):
        req = QueryRequest(
            metric="weeks_of_cover",
            grains=["distributor", "product"],
            tenant_id="default",
        )
        hr = await a3_stock.handle_a3(db, req, metric_key="weeks_of_cover")
    live.assert_not_awaited()
    assert hr.value == pytest.approx(10.0)
    assert hr.data_vintage and hr.data_vintage.get("woc_source") == "observations"
    assert hr.scorecard and hr.scorecard.get("missing_data_alert") is False


@pytest.mark.anyio
async def test_a1_handler_shipped_only_invariant():
    from app.query.handlers import a1_pve

    db = AsyncMock()
    payload = {
        "data_unavailable": False,
        "period_from": "26Q2",
        "period_to": "26Q2",
        "scorecard": {
            "fill_rate": 0.82,
            "line_hit_rate": 0.5,
            "planned_units": 100,
            "shipped_units_in_plan": 80,
            "pipeline_units_in_plan": 20,
            "short_exposure_units": 20,
            "over_plan_intake_units": 5,
            "deal_stock_units": 5,
            "unplanned_intake_units": 3,
            "no_po_blind_spot": {"line_count": 1, "planned_units": 10},
        },
        "volume_bias": {"by_bu": []},
        "drill_rows": [],
    }
    with patch(
        "app.query.handlers.a1_pve.plan_vs_executed_read_model",
        new_callable=AsyncMock,
        return_value=payload,
    ):
        req = QueryRequest(metric="fill_rate", grains=["period"], filters={"period_from": "26Q2"})
        hr = await a1_pve.handle_a1(db, req, metric_key="fill_rate")
    assert hr.status == "ok"
    assert "shipped_only_fill" in hr.invariants_applied
    assert hr.value == pytest.approx(0.82)


@pytest.mark.anyio
async def test_execute_caches_ok_result():
    db = AsyncMock()
    hr = HandlerResult(
        status="ok",
        invariants_applied=["latest_per_distributor_product_soh"],
        value=42.0,
        rows=[{"distributor_id": 1, "product_id": 2, "value": 42.0}],
    )
    with patch(
        "app.query.engine.dispatch_handler",
        new_callable=AsyncMock,
        return_value=("a3_stock", hr),
    ):
        r1 = await execute_query(
            db,
            metric="channel_stock",
            grains=["distributor", "product"],
        )
        r2 = await execute_query(
            db,
            metric="channel_stock",
            grains=["distributor", "product"],
        )
    assert r1.cache and r1.cache.hit is False
    assert r2.cache and r2.cache.hit is True
    assert r2.value == 42.0


def test_cache_key_stable():
    k1 = cache_key(
        tenant_id="default",
        metric="fill_rate",
        grains=["bu", "period"],
        filters={"period_from": "26Q1"},
        catalog_version=1,
    )
    k2 = cache_key(
        tenant_id="default",
        metric="fill_rate",
        grains=["period", "bu"],
        filters={"period_from": "26Q1"},
        catalog_version=1,
    )
    assert k1 == k2
    set_cached(k1, {"ok": True, "value": 1})
    assert get_cached(k1)["value"] == 1


def test_p3_1_validate_still_owns_grain_rules():
    r = validate_metric_grain("channel_stock", ["lineup_quarter"])
    assert r.ok is False
