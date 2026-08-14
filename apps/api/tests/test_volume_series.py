"""Unit 14A — calendar period_grain, volume series contract, grain refusals."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.query.calendar_grain import (
    bucket_end,
    bucket_start_to_key,
    coarsest_stored_rank,
    parse_period_bound,
    series_point,
)
from app.query.engine import execute_query
from app.query.handlers.volume_series import handle_volume
from app.query.types import QueryRequest
from app.semantics.registry import clear_catalog_cache, validate_metric_grain


@pytest.fixture(autouse=True)
def _catalog():
    clear_catalog_cache()
    yield
    clear_catalog_cache()


def test_calendar_helpers_week_month_quarter():
    monday = date(2026, 8, 10)  # ISO week 2026-W33
    assert bucket_start_to_key(monday, "week") == "2026-W33"
    assert bucket_end(monday, "week") == date(2026, 8, 16)
    month = date(2026, 8, 1)
    assert bucket_start_to_key(month, "month") == "2026-08"
    assert bucket_end(month, "month") == date(2026, 8, 31)
    q = date(2026, 4, 1)
    assert bucket_start_to_key(q, "quarter") == "2026-Q2"
    assert bucket_end(q, "quarter") == date(2026, 6, 30)
    assert parse_period_bound("26Q2", end=False) == date(2026, 4, 1)
    assert parse_period_bound("26Q2", end=True) == date(2026, 6, 30)
    pt = series_point(monday, "week", 12.5)
    assert pt["bucket_key"] == "2026-W33"
    assert pt["value"] == 12.5


def test_cst_stored_rank_week_vs_month():
    assert coarsest_stored_rank(["weekly"]) == 1
    assert coarsest_stored_rank(["weekly", "monthly"]) == 2


def test_sellout_units_valid_period_defaults_quarter():
    r = validate_metric_grain("sellout_units", ["period"])
    assert r.ok is True
    assert r.period_grain == "quarter"
    r2 = validate_metric_grain("sellout_units", ["period"], period_grain="week")
    assert r2.ok is True
    assert r2.period_grain == "week"


def test_sellout_units_refuses_daily():
    r = validate_metric_grain("sellout_units", ["period"], period_grain="day")
    assert r.ok is False
    assert "week" in r.message.lower()


def test_sellout_units_refuses_site_label():
    r = validate_metric_grain("sellout_units", ["site_label"])
    assert r.ok is False


def test_cst_refuses_distributor_product():
    r = validate_metric_grain("cst_sellthrough_units", ["distributor", "product"])
    assert r.ok is False


def test_fill_rate_refuses_period_grain():
    r = validate_metric_grain("fill_rate", ["period"], period_grain="week")
    assert r.ok is False
    assert "calendar-period" in r.message.lower() or "lineup" in r.message.lower()


def test_period_grain_without_period_dimension_refused():
    r = validate_metric_grain("sellout_units", ["customer"], period_grain="week")
    assert r.ok is False
    assert "requires period" in r.message.lower()


def test_two_metrics_in_one_key_refused():
    r = validate_metric_grain("sellout_units,cst_sellthrough_units", ["period"])
    assert r.ok is False
    assert "one governed metric" in r.message.lower()


def test_cst_by_customer_valid():
    r = validate_metric_grain("cst_sellthrough_units", ["customer"])
    assert r.ok is True
    assert r.period_grain is None


@pytest.mark.anyio
async def test_execute_refuses_daily_without_db():
    db = AsyncMock()
    result = await execute_query(
        db,
        metric="sellout_units",
        grains=["period"],
        period_grain="daily",
    )
    assert result.status == "refused"
    assert result.ok is False
    db.execute.assert_not_called()


@pytest.mark.anyio
async def test_explain_volume_no_db():
    db = AsyncMock()
    result = await execute_query(
        db,
        metric="sellout_units",
        grains=["period"],
        period_grain="week",
        explain_only=True,
    )
    assert result.status == "ok"
    assert result.handler == "volume_series"
    assert result.period_grain == "week"
    db.execute.assert_not_called()


class _Row:
    def __init__(self, **kwargs):
        self._mapping = kwargs

    def __getitem__(self, idx):
        return list(self._mapping.values())[idx]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.anyio
async def test_dsi_week_series_ordered():
    db = AsyncMock()
    w1 = date(2026, 8, 3)
    w2 = date(2026, 8, 10)
    db.execute = AsyncMock(
        return_value=_Result(
            [
                _Row(bucket_start=w1, value=10),
                _Row(bucket_start=w2, value=7),
            ]
        )
    )
    req = QueryRequest(
        metric="sellout_units",
        grains=["period"],
        period_grain="week",
        tenant_id="default",
    )
    hr = await handle_volume(db, req, metric_key="sellout_units")
    assert hr.status == "ok"
    assert hr.series is not None
    keys = [p["bucket_key"] for p in hr.series]
    assert keys == sorted(keys)
    assert keys[0].startswith("2026-W")
    assert hr.value == pytest.approx(17.0)
    assert "raw_units_not_velocity" in hr.invariants_applied


@pytest.mark.anyio
async def test_cst_customer_rows_no_series():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_Result(
            [
                _Row(value=100, customer_id=1),
                _Row(value=40, customer_id=2),
            ]
        )
    )
    req = QueryRequest(
        metric="cst_sellthrough_units",
        grains=["customer"],
        tenant_id="default",
    )
    hr = await handle_volume(db, req, metric_key="cst_sellthrough_units")
    assert hr.status == "ok"
    assert hr.series is None
    assert len(hr.rows or []) == 2
    assert hr.value == pytest.approx(140.0)


@pytest.mark.anyio
async def test_cst_week_refuses_monthly_stored():
    db = AsyncMock()

    async def _exec(stmt, *args, **kwargs):
        sql = str(stmt)
        if "period_type" in sql:
            return _Result([("monthly",)])
        raise AssertionError("should refuse before aggregate")

    db.execute = AsyncMock(side_effect=_exec)
    req = QueryRequest(
        metric="cst_sellthrough_units",
        grains=["period"],
        period_grain="week",
        tenant_id="default",
    )
    hr = await handle_volume(db, req, metric_key="cst_sellthrough_units")
    assert hr.status == "refused"
    assert "finer than stored" in (hr.message or "").lower()
