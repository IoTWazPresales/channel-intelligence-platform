"""Channel Operations API tests (mocked DB — no cip writes)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import channel_ops as co


@pytest.mark.anyio
async def test_summary_returns_zeros_on_empty_tables() -> None:
    db = AsyncMock()
    db.connection = AsyncMock(return_value=MagicMock())
    conn = await db.connection()
    conn.run_sync = AsyncMock(side_effect=lambda fn: fn(MagicMock(has_table=MagicMock(return_value=False))))

    scalar_results = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    db.scalar = AsyncMock(side_effect=scalar_results)
    db.execute = AsyncMock(return_value=MagicMock(one=MagicMock(return_value=(0, 0))))

    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(co, "latest_woc_observations", AsyncMock(return_value=[])):
                out = await co.channel_ops_summary(db)

    assert out["sell_out_this_quarter"]["units"] == 0
    assert out["sell_out_this_quarter"]["has_data"] is False
    assert out["total_inventory_units"] == 0
    assert out["sell_out_yoy_pct"] is None
    assert out["sell_out_data_vintage"]["current_quarter_has_data"] is False
    assert out["weeks_of_cover"] is None
    assert out["replenishment_threshold_weeks"] == 4.0
    assert out["replenishment_flag"] is False
    assert out["replenishment_pairs_below_threshold"] == 0
    assert out["has_velocity_data"] is False
    assert out["has_forecast_data"] is False
    assert out["woc_source"] == "observations"
    assert out["missing_data_alert"] is True


@pytest.mark.anyio
async def test_summary_yoy_none_when_prior_zero() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    # current quarter has units; prior year quarter is zero → YoY n/a
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(100.0, 50.0))),
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
        ]
    )
    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(
                co,
                "derived_stock_by_dist_product",
                AsyncMock(return_value={(1, 10): 20.0, (1, 11): 22.0}),
            ):
                with patch.object(
                    co,
                    "sellout_velocity_52wk_by_dist_product",
                    AsyncMock(return_value={(1, 10): 2.0, (1, 11): 3.0}),
                ):
                    out = await co.channel_ops_summary(db, woc_source="live")
    assert out["total_inventory_units"] == 42
    assert out["sell_out_yoy_pct"] is None
    assert out["weeks_of_cover"] == 42 / 5.0
    assert out["velocity_grain"] == "distributor_product"
    # pair (1,10): 20/2=10w — not below 4; (1,11): 22/3≈7.3 — not below
    assert out["replenishment_pairs_below_threshold"] == 0
    assert out["replenishment_flag"] is False  # portfolio 8.4w


@pytest.mark.anyio
async def test_summary_yoy_none_when_current_quarter_has_no_coverage() -> None:
    """Freshness: empty current quarter must not show −100% YoY vs prior-year volume."""
    db = AsyncMock()
    # count=0 (no rows in current quarter), then max sell-out date, then later scalars
    db.scalar = AsyncMock(side_effect=[0, date(2026, 6, 12)] + [0] * 20)
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
            MagicMock(one=MagicMock(return_value=(27980.0, 1.0))),
        ]
    )
    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(co, "latest_woc_observations", AsyncMock(return_value=[])):
                out = await co.channel_ops_summary(db)
    assert out["sell_out_this_quarter"]["units"] == 0
    assert out["sell_out_this_quarter"]["has_data"] is False
    assert out["sell_out_prior_year_quarter"]["units"] == 27980.0
    assert out["sell_out_yoy_pct"] is None
    assert out["sell_out_data_vintage"]["max_transaction_date"] == "2026-06-12"
    assert out["sell_out_data_vintage"]["current_quarter_has_data"] is False


@pytest.mark.anyio
async def test_summary_woc_never_uses_customer_velocity_avg() -> None:
    """Guard against regressing to stock ÷ avg(FactCustomerVelocity) (~78k weeks on cip)."""
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
        ]
    )
    stock = {(7, 1): 100.0, (7, 2): 50.0}
    vel = {(7, 1): 10.0, (7, 2): 5.0}

    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(co, "derived_stock_by_dist_product", AsyncMock(return_value=stock)):
                with patch.object(
                    co,
                    "sellout_velocity_52wk_by_dist_product",
                    AsyncMock(return_value=vel),
                ) as vel_fn:
                    out = await co.channel_ops_summary(db, woc_source="live")

    vel_fn.assert_awaited_once()
    assert out["velocity_grain"] == "distributor_product"
    assert out["weeks_of_cover"] == pytest.approx(10.0)
    assert out["total_inventory_units"] == 150


@pytest.mark.anyio
async def test_summary_replenishment_pairs_below_threshold() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
        ]
    )
    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(
                co,
                "derived_stock_by_dist_product",
                AsyncMock(return_value={(1, 10): 6.0, (1, 11): 40.0}),
            ):
                with patch.object(
                    co,
                    "sellout_velocity_52wk_by_dist_product",
                    AsyncMock(return_value={(1, 10): 3.0, (1, 11): 2.0}),
                ):
                    out = await co.channel_ops_summary(db, woc_source="live")
    # 6/3=2w → flag; 40/2=20w → no; portfolio 46/5=9.2 → no
    assert out["replenishment_pairs_below_threshold"] == 1
    assert out["replenishment_flag"] is False
    assert out["replenishment_threshold_weeks"] == 4.0


@pytest.mark.anyio
async def test_summary_reads_observations_not_live_calculator() -> None:
    from app.services.woc_observation_read import WocObservationRow

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
            MagicMock(one=MagicMock(return_value=(0.0, 0.0))),
        ]
    )
    obs = [
        WocObservationRow(
            distributor_id=1,
            product_id=10,
            snapshot_date=date(2026, 8, 10),
            cover_as_of_date=date(2026, 8, 17),
            reported_soh=100,
            sell_out_since=10,
            landed_since=5,
            derived_stock=95,
            weekly_velocity=10.0,
            weeks_of_cover=9.5,
            replenishment_flag=False,
            replenishment_threshold_weeks=4.0,
            trigger="as_of_backfill",
            formula_version="A3-02.v1",
            params={},
            data_vintage={},
            import_job_id=None,
        )
    ]
    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(co, "latest_woc_observations", AsyncMock(return_value=obs)):
                with patch.object(
                    co, "derived_stock_by_dist_product", AsyncMock(return_value={(9, 9): 999.0})
                ) as live:
                    out = await co.channel_ops_summary(db)
    live.assert_not_awaited()
    assert out["woc_source"] == "observations"
    assert out["total_inventory_units"] == 95
    assert out["weeks_of_cover"] == pytest.approx(9.5)
    assert out["missing_data_alert"] is False


@pytest.mark.anyio
async def test_sell_out_filters_by_distributor_id() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    await co.channel_ops_sell_out(db, distributor_id=42, page=1, page_size=50, user=None)
    assert db.scalar.called


@pytest.mark.anyio
async def test_inventory_returns_400_when_distributor_id_missing() -> None:
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await co.channel_ops_inventory(db, distributor_id=None)
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_forecasts_reads_fact_dsi_forecast_not_fact_forecast() -> None:
    db = AsyncMock()
    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        out = await co.channel_ops_forecasts(db, distributor_id=1)
    assert out["items"] == []
    assert "fact_forecast" not in str(co.FactDsiForecast.__tablename__)


@pytest.mark.anyio
async def test_movements_returns_400_when_distributor_id_missing() -> None:
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await co.channel_ops_movements(db, distributor_id=None)
    assert exc.value.status_code == 400


def test_lab_woc_bucket_and_cover_status_match_design_lab() -> None:
    assert co._lab_woc_bucket(None) is None
    assert co._lab_woc_bucket(0.4) == "<1w"
    assert co._lab_woc_bucket(1.5) == "1–2w"
    assert co._lab_woc_bucket(3) == "2–4w"
    assert co._lab_woc_bucket(5) == "4–6w"
    assert co._lab_woc_bucket(7) == "6–8w"
    assert co._lab_woc_bucket(8) == "8w+"
    assert co._cover_pair_status(1.9) == "breach"
    assert co._cover_pair_status(2) == "watch"
    assert co._cover_pair_status(8) == "ok"
    assert co._cover_pair_status(8.1) == "excess"
    assert co._cover_pair_status(None) is None
