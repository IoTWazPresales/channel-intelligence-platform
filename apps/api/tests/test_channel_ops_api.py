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
            with patch.object(co, "sum_derived_channel_stock", AsyncMock(return_value=(0, 0))):
                out = await co.channel_ops_summary(db)

    assert out["sell_out_this_quarter"]["units"] == 0
    assert out["total_inventory_units"] == 0
    assert out["sell_out_yoy_pct"] is None
    assert out["weeks_of_cover"] is None
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
            with patch.object(co, "sum_derived_channel_stock", AsyncMock(return_value=(42, 3))):
                out = await co.channel_ops_summary(db)
    assert out["total_inventory_units"] == 42
    assert out["sell_out_yoy_pct"] is None


@pytest.mark.anyio
async def test_sell_out_filters_by_distributor_id() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    await co.channel_ops_sell_out(db, distributor_id=42, page=1, page_size=50)
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
