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
                out = await co.channel_ops_summary(db, period_grain="quarter", weeks=13)

    assert out["sell_out_this_quarter"]["units"] == 0
    assert out["total_inventory_units"] == 0
    assert out["sell_out_yoy_pct"] is None
    assert out["weeks_of_cover"] is None
    assert out["has_velocity_data"] is False
    assert out["has_forecast_data"] is False
    assert out["business_unit_applies_to"] == ["all"]


@pytest.mark.anyio
async def test_summary_business_unit_applies_to_flags_partial_cohort() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(return_value=MagicMock(one=MagicMock(return_value=(0, 0))))
    with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
        with patch.object(co, "_has_rows", AsyncMock(return_value=False)):
            with patch.object(co, "sum_derived_channel_stock", AsyncMock(return_value=(0, 0))):
                out = await co.channel_ops_summary(
                    db, business_unit="NB", period_grain="quarter", weeks=13
                )
    assert out["business_unit"] == "NB"
    assert out["business_unit_applies_to"] == [
        "sell_out_units",
        "sell_out_revenue",
        "sell_out_yoy",
    ]


@pytest.mark.anyio
async def test_sell_out_accepts_spec_search_param() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    await co.channel_ops_sell_out(db, spec_search="16GB", page=1, page_size=50)
    assert db.scalar.called


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
                out = await co.channel_ops_summary(db, period_grain="quarter", weeks=13)
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
async def test_inventory_truncates_when_over_cap() -> None:
    db = AsyncMock()
    cap = co.INVENTORY_LIST_CAP
    derived = [
        {
            "product_id": i,
            "distributor_id": 1,
            "snapshot_date": None,
            "reported_soh": 1.0,
            "sell_out_since": 0.0,
            "landed_since": 0.0,
            "derived_stock": 1.0,
            "calculated_soh": None,
            "variance_units": None,
            "reconciliation_status": None,
        }
        for i in range(cap + 50)
    ]
    with patch.object(co, "derived_stock_rows_for_distributor", AsyncMock(return_value=derived)):
        with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
            db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            db.scalar = AsyncMock(return_value="Dist One")
            out = await co.channel_ops_inventory(db, distributor_id=1, page=1, page_size=50)
    assert out["true_total"] == cap + 50
    assert out["total"] == cap
    assert out["truncated"] is True
    assert out["page"] == 1
    assert out["page_size"] == 50
    assert len(out["items"]) == 50


@pytest.mark.anyio
async def test_inventory_pages_offset() -> None:
    db = AsyncMock()
    derived = [
        {
            "product_id": i,
            "distributor_id": 1,
            "snapshot_date": None,
            "reported_soh": float(i),
            "sell_out_since": 0.0,
            "landed_since": 0.0,
            "derived_stock": float(i),
            "calculated_soh": None,
            "variance_units": None,
            "reconciliation_status": None,
        }
        for i in range(120)
    ]
    with patch.object(co, "derived_stock_rows_for_distributor", AsyncMock(return_value=derived)):
        with patch.object(co, "_table_exists", AsyncMock(return_value=False)):
            db.execute = AsyncMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[(i, f"SKU-{i}", f"P-{i}") for i in range(120)])
                )
            )
            db.scalar = AsyncMock(return_value="Dist One")
            out = await co.channel_ops_inventory(db, distributor_id=1, page=2, page_size=50)
    assert out["total"] == 120
    assert out["page"] == 2
    assert len(out["items"]) == 50
    assert out["items"][0]["product_id"] == 50


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
