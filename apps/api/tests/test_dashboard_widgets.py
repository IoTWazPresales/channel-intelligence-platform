"""Unit 14B — dashboard widget persist helpers (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.dashboard_widgets import default_layout, validate_widget_query, widget_to_dict
from app.semantics.registry import clear_catalog_cache


@pytest.fixture(autouse=True)
def _catalog():
    clear_catalog_cache()
    yield
    clear_catalog_cache()


def test_default_layout_two_column():
    a = default_layout(0)
    b = default_layout(1)
    assert a == {"x": 0, "y": 0, "w": 6, "h": 8}
    assert b["x"] == 6
    assert b["y"] == 0


def test_widget_to_dict_round_trip_fields():
    row = SimpleNamespace(
        id=9,
        dashboard_id=3,
        tenant_id="default",
        title="Sell-out by week",
        visual="line",
        metric_key="sellout_units",
        grains=["period"],
        filters={},
        period_grain="week",
        layout_json={"x": 0, "y": 0, "w": 6, "h": 8},
        saved_report_id=None,
        sort_order=0,
        created_at=None,
        updated_at=None,
    )
    d = widget_to_dict(row)
    assert d["metric_key"] == "sellout_units"
    assert d["period_grain"] == "week"
    assert d["visual"] == "line"
    assert d["layout_json"]["w"] == 6
    assert d["saved_report_id"] is None


def test_validate_widget_sellout_week_ok():
    v = validate_widget_query(
        metric="sellout_units",
        grains=["period"],
        period_grain="week",
        visual="line",
        tenant_id="default",
    )
    assert v.ok is True
    assert v.period_grain == "week"


def test_validate_widget_cst_customer_ok():
    v = validate_widget_query(
        metric="cst_sellthrough_units",
        grains=["customer"],
        period_grain=None,
        visual="bar",
        tenant_id="default",
    )
    assert v.ok is True
    assert v.period_grain is None


def test_validate_widget_refuses_daily():
    with pytest.raises(HTTPException) as ei:
        validate_widget_query(
            metric="sellout_units",
            grains=["period"],
            period_grain="day",
            visual="line",
            tenant_id="default",
        )
    assert ei.value.status_code == 400


def test_validate_widget_refuses_unknown_visual():
    with pytest.raises(HTTPException) as ei:
        validate_widget_query(
            metric="sellout_units",
            grains=["period"],
            period_grain="week",
            visual="heatmap",
            tenant_id="default",
        )
    assert ei.value.status_code == 400
    assert "visual" in str(ei.value.detail).lower()
