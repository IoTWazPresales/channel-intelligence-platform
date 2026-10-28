"""E7 models and E8 day / calendar / calculated measures. No database."""

from datetime import date

from app.query.model import compiler
from app.query.model.compiler import compile_plan
from app.query.model.graph import DAILY_REFUSAL, V2Request, plan_request
from app.query.model.loader import clear_model_cache, default_model
from app.semantics.registry import load_catalog
from app.services.business_calendar import BusinessCalendar


def setup_function() -> None:
    clear_model_cache()


def _plan(measures, breakdowns=(), grain=None, **kw):
    dm = default_model()
    req = V2Request(measures=list(measures), breakdowns=list(breakdowns), period_grain=grain, **kw)
    return dm, plan_request(dm, req, v1_catalog=load_catalog())


def test_new_models_plan_on_their_own_facts():
    dm = default_model()
    assert set(dm.models) >= {"returns", "sellin", "shipments", "distributor_stock", "lineup", "recorded_prices"}
    pending = {p["id"] for p in dm.pending}
    assert "returns" not in pending
    assert "shipments" not in pending
    for measure, breakdowns in (
        ("returns.units", ["product"]),
        ("sellin.units", ["distributor"]),
        ("shipments.quantity", ["product"]),
        ("lineup.units", ["product"]),
        ("recorded_prices.net_price_avg", ["currency"]),
    ):
        _, plan = _plan([measure], breakdowns)
        assert plan.ok, plan.refusals
    _, stock = _plan(["distributor_stock.on_hand"], ["distributor", "product"])
    assert stock.ok, stock.refusals
    _, summed = _plan(["distributor_stock.on_hand"], ["period"], "month")
    assert not summed.ok


def test_day_is_allowed_on_a_day_fact_and_refused_for_sell_through():
    _, day = _plan(["dsi_sellout.units"], ["period"], "day")
    assert day.ok and day.period_grain == "day"
    _, cst = _plan(["cst_sellthrough.units"], ["period"], "day")
    assert not cst.ok
    assert cst.refusals[0].reason == DAILY_REFUSAL


def test_prior_year_running_total_and_share_compile():
    dm, missing = _plan(["dsi_sellout.units_prior_year"])
    assert not missing.ok
    _, plan = _plan(
        ["dsi_sellout.units", "dsi_sellout.units_prior_year", "dsi_sellout.units_running_total", "dsi_sellout.units_share"],
        ["period"],
        "month",
        period_from="2026-03-01",
        period_to="2026-04-30",
    )
    assert plan.ok
    sql = compile_plan(dm, plan, tenant_id="example").sql_text()
    assert "yearago" in sql
    assert "interval '1 year'" in sql
    assert "prior_year_from" in sql
    assert "OVER" in sql.upper()


def test_retail_calendar_buckets_replace_date_trunc():
    dm, plan = _plan(["dsi_sellout.units"], ["period"], "month")
    cal = BusinessCalendar({"type": "retail_445", "fiscal_year_start_month": 1})
    sql = compile_plan(dm, plan, tenant_id="example", calendar=cal).sql_text()
    # The retail bucket runs on distinct days. The retail bucket itself is not a date_trunc.
    assert "date_trunc('day'" in sql
    assert "date_trunc('month'" not in sql
    assert "date_trunc('quarter'" not in sql
    assert "date_trunc('year'" not in sql
    assert "bkt_month_" not in sql
    assert "make_date" in sql


def test_retail_week_bucket_is_not_a_thousand_arm_case():
    dm, plan = _plan(["dsi_sellout.units"], ["period"], "week")
    cal = BusinessCalendar({"type": "retail_445", "week_start_day": 6})
    sql = compile_plan(dm, plan, tenant_id="example", calendar=cal).sql_text()
    assert "bkt_week_" not in sql
    assert len(sql) < 8000
    assert "isodow" in sql


def test_shipments_count_shipped_lines_on_the_resolved_customer():
    dm, plan = _plan(["shipments.quantity", "shipments.lines"], ["customer"])
    assert plan.ok, plan.refusals
    sql = compile_plan(dm, plan, tenant_id="example").sql_text()
    assert "f.resolved_customer_id" in sql
    assert "f.customer_id" not in sql
    assert "ship_confirm_date IS NOT NULL" in sql
    assert "counted_qty" not in sql
    assert "MATERIALIZED" not in sql


def test_open_shipments_use_the_twin_remainder_and_refuse_a_period():
    dm, plan = _plan(["shipments.open_quantity", "shipments.open_lines"], ["customer"])
    assert plan.ok, plan.refusals
    sql = compile_plan(dm, plan, tenant_id="example").sql_text()
    assert "f.resolved_customer_id" in sql
    assert "f.customer_id" not in sql
    assert "counted_qty" in sql
    assert "MATERIALIZED" in sql
    _, refused = _plan(["shipments.open_quantity"], ["period"], "month")
    assert not refused.ok
    assert refused.measures == []
    assert "period" in refused.refusals[0].reason
    _, windowed = _plan(
        ["shipments.open_quantity"],
        ["customer"],
        period_from="2026-01-01",
        period_to="2026-03-31",
    )
    assert not windowed.ok
    _, mixed = _plan(["shipments.quantity", "shipments.open_quantity"], ["period"], "month")
    assert mixed.ok
    assert [m.id for m in mixed.measures] == ["shipments.quantity"]
    assert any(r.measure == "shipments.open_quantity" for r in mixed.refusals)


def test_retail_prior_year_receives_the_bucket_start(monkeypatch):
    seen = []
    real = compiler.prior_year_bucket_expr

    def spy(col, grain, calendar):
        seen.append(col)
        return real(col, grain, calendar)

    monkeypatch.setattr(compiler, "prior_year_bucket_expr", spy)
    cal = BusinessCalendar({"type": "retail_445"})
    for grain in ("week", "month"):
        seen.clear()
        dm, plan = _plan(
            ["dsi_sellout.units", "dsi_sellout.units_prior_year"],
            ["period"],
            grain,
            period_from="2026-03-01",
            period_to="2026-04-30",
        )
        assert plan.ok, plan.refusals
        compile_plan(dm, plan, tenant_id="example", calendar=cal)
        assert seen, grain
        assert all(col.key == "bucket_start" for col in seen), grain


def test_the_same_custom_calendar_request_compiles_to_the_same_sql():
    periods = []
    cursor = date(2024, 1, 5)
    for _ in range(24):
        periods.append({
            "start": cursor.isoformat(),
            "fiscal_year": cursor.year,
            "quarter": (cursor.month - 1) // 3 + 1,
        })
        month = cursor.month + 1
        year = cursor.year + (1 if month > 12 else 0)
        cursor = date(year, 1 if month > 12 else month, 5)
    cal = BusinessCalendar({"type": "custom", "custom_periods": periods})
    dm, plan = _plan(
        ["dsi_sellout.units", "dsi_sellout.units_prior_year"],
        ["period"],
        "month",
        period_from="2026-03-01",
        period_to="2026-04-30",
    )
    assert plan.ok, plan.refusals
    first = compile_plan(dm, plan, tenant_id="example", calendar=cal).sql_text()
    second = compile_plan(dm, plan, tenant_id="example", calendar=cal).sql_text()
    assert first == second
    assert "cumonth_0_from" in first
    assert "cyst_0_from" in first
