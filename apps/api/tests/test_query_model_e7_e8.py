"""E7 models and E8 day / calendar / calculated measures. No database."""

from app.query.model.compiler import compile_plan
from app.query.model.graph import DAILY_REFUSAL, V2Request, plan_request
from app.query.model.loader import clear_model_cache, default_model
from app.semantics.registry import load_catalog
from app.services.business_calendar import BusinessCalendar


def setup_function() -> None:
    clear_model_cache()


def _plan(measures, breakdowns=(), grain=None):
    dm = default_model()
    req = V2Request(measures=list(measures), breakdowns=list(breakdowns), period_grain=grain)
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
    )
    assert plan.ok
    sql = compile_plan(dm, plan, tenant_id="example").sql_text()
    assert "yearago" in sql
    assert "interval '1 year'" in sql
    assert "OVER" in sql.upper()


def test_retail_calendar_buckets_replace_date_trunc():
    dm, plan = _plan(["dsi_sellout.units"], ["period"], "month")
    cal = BusinessCalendar({"type": "retail_445", "fiscal_year_start_month": 1})
    sql = compile_plan(dm, plan, tenant_id="example", calendar=cal).sql_text()
    assert "date_trunc" not in sql
    assert "bkt_month_0" in sql
