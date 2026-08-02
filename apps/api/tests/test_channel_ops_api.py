"""Channel Operations API tests (mocked DB — no cip writes)."""

from __future__ import annotations

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
            with patch.object(co, "derived_stock_by_dist_product", AsyncMock(return_value={})):
                with patch.object(
                    co, "sellout_velocity_52wk_by_dist_product", AsyncMock(return_value={})
                ):
                    out = await co.channel_ops_summary(db)

    assert out["sell_out_this_quarter"]["units"] == 0
    assert out["total_inventory_units"] == 0
    assert out["sell_out_yoy_pct"] is None
    assert out["weeks_of_cover"] is None
    assert out["replenishment_threshold_weeks"] == 4.0
    assert out["replenishment_flag"] is False
    assert out["replenishment_pairs_below_threshold"] == 0
    assert out["has_velocity_data"] is False
    assert out["has_forecast_data"] is False


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
                    out = await co.channel_ops_summary(db)
    assert out["total_inventory_units"] == 42
    assert out["sell_out_yoy_pct"] is None
    assert out["weeks_of_cover"] == 42 / 5.0
    assert out["velocity_grain"] == "distributor_product"
    # pair (1,10): 20/2=10w — not below 4; (1,11): 22/3≈7.3 — not below
    assert out["replenishment_pairs_below_threshold"] == 0
    assert out["replenishment_flag"] is False  # portfolio 8.4w


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
                    out = await co.channel_ops_summary(db)

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
                    out = await co.channel_ops_summary(db)
    # 6/3=2w → flag; 40/2=20w → no; portfolio 46/5=9.2 → no
    assert out["replenishment_pairs_below_threshold"] == 1
    assert out["replenishment_flag"] is False
    assert out["replenishment_threshold_weeks"] == 4.0


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
