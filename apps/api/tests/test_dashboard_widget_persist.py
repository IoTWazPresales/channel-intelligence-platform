"""Unit 14B live persist — two widgets on cip (ALLOW_TESTS_ON_DEV_DB=1)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.saved_reports import Dashboard, DashboardWidget
from app.services.dashboard_widgets import default_layout


pytestmark = pytest.mark.skipif(
    os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() != "1",
    reason="Live dashboard_widget INSERT requires ALLOW_TESTS_ON_DEV_DB=1",
)


def test_persist_two_widgets_reload_geometry():
    db = SessionLocal()
    dash_id = None
    try:
        db_name = db.execute(text("SELECT current_database()")).scalar()
        assert db_name == "cip"
        dash = Dashboard(
            tenant_id="default",
            owner_user_id=None,
            name="unit14b-widget-persist",
            visibility="personal",
            shared_roles=[],
        )
        db.add(dash)
        db.flush()
        dash_id = int(dash.id)
        w1 = DashboardWidget(
            dashboard_id=dash.id,
            tenant_id="default",
            title="Sell-out by week",
            visual="line",
            metric_key="sellout_units",
            grains=["period"],
            filters={},
            period_grain="week",
            layout_json=default_layout(0),
            sort_order=0,
        )
        w2 = DashboardWidget(
            dashboard_id=dash.id,
            tenant_id="default",
            title="CST sell-through by customer",
            visual="bar",
            metric_key="cst_sellthrough_units",
            grains=["customer"],
            filters={},
            period_grain=None,
            layout_json=default_layout(1),
            sort_order=1,
        )
        db.add_all([w1, w2])
        db.commit()

        rows = (
            db.query(DashboardWidget)
            .filter(DashboardWidget.dashboard_id == dash_id)
            .order_by(DashboardWidget.sort_order)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].metric_key == "sellout_units"
        assert rows[0].period_grain == "week"
        assert rows[0].visual == "line"
        assert rows[0].layout_json["x"] == 0
        assert rows[1].metric_key == "cst_sellthrough_units"
        assert rows[1].grains == ["customer"]
        assert rows[1].visual == "bar"
        assert rows[1].layout_json["x"] == 6
        assert db.execute(text("SELECT to_regclass('public.dashboard_tile')")).scalar() is None
    finally:
        if dash_id is not None:
            db.rollback()
            db.query(DashboardWidget).filter(DashboardWidget.dashboard_id == dash_id).delete()
            db.query(Dashboard).filter(Dashboard.id == dash_id).delete()
            db.commit()
        db.close()
