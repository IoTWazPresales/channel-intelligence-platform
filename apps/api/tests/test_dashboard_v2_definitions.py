"""N-0116: stored v2 definitions, catalog filter_refusals / honours, migration 0048, migration script,
starter templates, report delivery on the dual path.

No-DB tests check the planner-backed rules. DB tests run on cip_test inside one transaction that is
rolled back (DDL included: Postgres DDL is transactional).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.query.cache import clear_query_cache
from app.query.model.catalog import catalog_v2
from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import default_model
from app.semantics.registry import clear_catalog_cache, load_catalog
from app.services.dashboard_definitions import (
    DefinitionRefused,
    check_dashboard_filters,
    check_definition,
    definition_from_v1,
    effective_visual_v1,
    request_from_definition,
    runs_v1,
)

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_catalog():
    clear_catalog_cache()
    yield
    clear_catalog_cache()


def _cat():
    return catalog_v2(default_model(), load_catalog(), is_admin=False)


# ----------------------------------------------------------------------------- S5 catalog


def test_catalog_filter_refusals_are_the_planners_own_texts() -> None:
    dm, v1 = default_model(), load_catalog()
    models = {m["id"]: m for m in _cat()["models"]}
    cases = [("cst_sellthrough", "cst_sellthrough.units", "distributor", "W-CST-NO-DISTRIBUTOR"),
             ("dsi_sellout", "dsi_sellout.units", "site_label", "W-SITE-CST-ONLY")]
    for model_id, measure, bid, wall in cases:
        reason = models[model_id]["filter_refusals"][bid]
        assert reason == dm.wall(wall).reason
        plan = plan_request(dm, V2Request(measures=[measure], filters={bid: [1] if bid == "distributor" else ["x"]}), v1_catalog=v1)
        assert not plan.measures
        assert plan.refusals[0].reason == f"Filter {bid!r}: {reason}"
    # Allowed breakdowns are never listed; period is not a filter.
    for m in models.values():
        assert not set(m["filter_refusals"]) & set(m["breakdowns"])
        assert "period" not in m["filter_refusals"]


def test_catalog_governed_honours_and_planner_refuses_what_is_not_honoured() -> None:
    dm, v1 = default_model(), load_catalog()
    by_id = {m["id"]: m for m in _cat()["measures"]}
    woc = by_id["weeks_of_cover"]["honours"]
    assert woc["filters"] == ["distributor", "product"] and woc["dates"] is False and woc["handler"] == "a3_stock"
    pipe = by_id["pipeline_inbound"]["honours"]
    assert pipe["filters"] == ["bu"] and pipe["dates"] is True and pipe["all_time_only"] is False
    spend = by_id["support_spend"]["honours"]
    assert spend["filters"] == ["bu", "customer"] and spend["all_time_only"] is True
    assert "honours" not in by_id["dsi_sellout.units"]

    def plan(measure, breakdowns, **kw):
        return plan_request(dm, V2Request(measures=[measure], breakdowns=breakdowns, **kw), v1_catalog=v1)

    p = plan("weeks_of_cover", ["distributor", "product"], filters={"customer": 1})
    assert p.governed is None and p.refusals[0].reason == "Weeks of cover cannot be filtered by customer: the figure is worked out without it."
    p = plan("pipeline_inbound", ["period"], filters={"customer": 1})
    assert p.governed is None and "cannot be filtered by customer" in p.refusals[0].reason
    p = plan("pipeline_inbound", ["period"], filters={"bu": "Notebook"})
    assert p.governed is not None and p.governed_filters == {"bu": "Notebook"}
    p = plan("weeks_of_cover", ["distributor", "product"], period_from="2026-01-01")
    assert p.governed is None and "cannot be filtered by dates" in p.refusals[0].reason


# ----------------------------------------------------------------------------- definitions


def test_widget_fixed_window_is_validated_preserved_and_never_delivered_through_v1() -> None:
    fixed = {"from": "2026-01-01", "to": "2026-01-31"}
    c = check_definition({"query": {"measures": ["dsi_sellout.units"]},
                          "dashboard": {"ignore_filters": ["customer"], "fixed_window": fixed}}, tenant_id="default")
    assert c.definition["dashboard"] == {"ignore_filters": ["customer"], "fixed_window": fixed}
    assert not c.v1_equivalent and not runs_v1(c.definition)
    req = request_from_definition(c.definition, period_from="2026-07-01", period_to="2026-07-31")
    assert (req.period_from, req.period_to) == (fixed["from"], fixed["to"])


@pytest.mark.parametrize("settings", [
    {"ignore_filters": ["unknown_filter"]}, {"ignore_filters": "customer"},
    {"fixed_window": {"from": "2026-02-30", "to": "2026-03-01"}},
    {"fixed_window": {"from": "2026-03-01", "to": "2026-01-01"}},
    {"fixed_window": {"from": "2026-01-01"}}, {"unknown": True},
])
def test_widget_dashboard_overrides_refuse_invalid_shapes(settings) -> None:
    with pytest.raises(DefinitionRefused, match="dashboard"):
        check_definition({"query": {"measures": ["dsi_sellout.units"]}, "dashboard": settings}, tenant_id="default")


def test_definition_valid_model_and_governed_with_v1_mirror() -> None:
    c = check_definition({"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["period"], "period": {"grain": "week"}}, "v1_equivalent": False}, tenant_id="default")
    assert c.definition == {"v": 1, "kind": "model", "query": {"measures": ["dsi_sellout.units"], "breakdowns": ["period"], "period": {"grain": "week"}}, "v1_equivalent": True}
    assert (c.v1.metric_key, c.v1.grains, c.v1.period_grain, c.v1.filters) == ("sellout_units", ["period"], "week", {})

    c = check_definition({"query": {"measures": ["cst_sellthrough.units"], "breakdowns": ["customer"], "filters": {"customer": [18]}}}, tenant_id="default")
    assert c.v1_equivalent and c.v1.filters == {"customer_id": 18}

    c = check_definition({"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["bu"], "filters": {"bu": ["Notebook"]}}}, tenant_id="default")
    assert c.v1_equivalent is False and c.v1.metric_key == "dsi_sellout.units" and c.v1.grains == [] and c.v1.period_grain is None

    c = check_definition({"query": {"measures": ["weeks_of_cover"], "breakdowns": ["distributor", "product"], "filters": {"product": 7}}}, tenant_id="default")
    assert c.definition["kind"] == "governed" and c.v1_equivalent and c.v1.filters == {"product_id": 7}

    # Year grain and two measures have no v1 equivalent.
    c = check_definition({"query": {"measures": ["dsi_sellout.units", "dsi_sellout.lines"], "breakdowns": ["period"], "period": {"grain": "year"}}}, tenant_id="default")
    assert c.v1_equivalent is False and c.v1.metric_key == "dsi_sellout.units"

    # A per-week rate takes its dates from the dashboard.
    c = check_definition({"query": {"measures": ["cst_sellthrough.units_per_week"]}}, tenant_id="default")
    assert c.needs_date_range is True and "period" not in c.definition["query"]


@pytest.mark.parametrize(
    "raw, needle",
    [
        ({"query": {"measures": ["dsi_sellout.units", "cst_sellthrough.units"]}}, "One query reads one model"),
        ({"query": {"measures": ["cst_sellthrough.units"], "filters": {"distributor": [3]}}}, "do not say which distributor"),
        ({"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["site_label"]}}, "site_label is CST-only"),  # kept v1 text
        ({"query": {"measures": ["dsi_sellout.units"], "limit": 5001}}, "above the maximum of 5000 rows"),
        ({"query": {"measures": ["sellout_units"]}}, "Use dsi_sellout.units"),
        ({"query": {"measures": ["nope.units"]}}, "Unknown measure"),
        ({"query": {"measures": ["dsi_sellout.units"], "period": {"grain": "week", "from": "2026-01-01"}}}, "never stores period.from"),
        ({"query": {"measures": ["dsi_sellout.units"]}, "extra": 1}, "Unknown key in definition_v2"),
        ({"v": 2, "query": {"measures": ["dsi_sellout.units"]}}, "definition_v2.v must be 1"),
        ({"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["period"], "period": {"grain": "day"}}}, "Lowest calendar grain is week"),
        ({"query": {"measures": ["cst_sellthrough.reported_soh"], "breakdowns": ["period"]}}, "never added up across dates"),
        ({"query": {"measures": ["dsi_sellout.units"]}, "display": {"top_n": 0}}, "top_n"),
        ({"query": {"measures": ["dsi_sellout.units"]}, "display": {"compare": "false"}}, "compare is true or false"),
    ],
)
def test_definition_refused_with_the_planners_text(raw, needle) -> None:
    with pytest.raises(DefinitionRefused) as exc:
        check_definition(raw, tenant_id="default")
    detail = exc.value.detail()
    assert needle in detail["message"] and detail["refusals"] and needle in detail["refusals"][0]["reason"]


def test_request_from_definition_and_dual_path_switch() -> None:
    d = {"v": 1, "kind": "model", "query": {"measures": ["dsi_sellout.units"], "breakdowns": ["period"], "period": {"grain": "week"}, "sort": {"by": "dsi_sellout.units", "dir": "desc"}, "limit": 50}}
    r = request_from_definition(d, period_from="2026-01-01", period_to="2026-03-31")
    assert (r.measures, r.breakdowns, r.period_grain, r.period_from, r.period_to, r.sort_by, r.sort_dir, r.limit) == (
        ["dsi_sellout.units"], ["period"], "week", "2026-01-01", "2026-03-31", "dsi_sellout.units", "desc", 50)
    assert runs_v1(None) and runs_v1({"v1_equivalent": True}) and not runs_v1({"v1_equivalent": False}) and not runs_v1({})


def test_dashboard_filters_json_checked() -> None:
    good = {"date": {"preset": "last_52_weeks", "from": None, "to": None}, "compare": "previous_period",
            "customer": [299], "distributor": [], "bu": ["Notebook"], "required": ["customer"], "category": ["X"]}
    assert check_dashboard_filters(good) == good
    for bad in ({"date": {"preset": "yesterday"}}, {"compare": "last_week"}, {"customer": 5}, {"nope": []},
                {"required": ["nope"]}, {"date": {"from": "soon"}}, {"period": []}, {"customer": [{"id": 1}]}):
        with pytest.raises(Exception) as exc:
            check_dashboard_filters(bad)
        assert getattr(exc.value, "status_code", None) == 400


# ----------------------------------------------------------------------------- S2 mapping (pure)

# The 9 rows on cip (spec s.1 / s.2.4).
CIP_ROWS = [
    ("W4", "sellout_units", ["period"], "week", "area", "model", ["dsi_sellout.units"], "week", "area"),
    ("W5", "cst_sellthrough_units", ["customer", "product"], None, "line", "model", ["cst_sellthrough.units"], None, "hbar"),
    ("W6", "cst_sellthrough_units", ["period"], "week", "line", "model", ["cst_sellthrough.units"], "week", "line"),
    ("W11", "sellout_units", ["distributor", "product"], None, "table", "model", ["dsi_sellout.units"], None, "table"),
    ("W19", "pipeline_inbound", ["period"], None, "kpi", "governed", ["pipeline_inbound"], None, "kpi"),
    ("W20", "cst_sellthrough_units", ["customer", "period"], "week", "line", "model", ["cst_sellthrough.units"], "week", "line"),
    ("R1", "weeks_of_cover", ["distributor", "product"], None, "kpi", "governed", ["weeks_of_cover"], None, "kpi"),
    ("R2", "weeks_of_cover", ["distributor", "product"], None, "kpi", "governed", ["weeks_of_cover"], None, "kpi"),
    ("R3", "sellout_units", ["period"], "week", "line", "model", ["dsi_sellout.units"], "week", "line"),
]


@pytest.mark.parametrize("tag, metric, grains, pg, visual, kind, measures, grain, visual_after", CIP_ROWS)
def test_definition_from_v1_maps_the_nine_cip_rows(tag, metric, grains, pg, visual, kind, measures, grain, visual_after) -> None:
    checked, after = definition_from_v1(metric_key=metric, grains=grains, filters={}, period_grain=pg, visual=visual, tenant_id="default", at="2026-10-23")
    d = checked.definition
    assert d["kind"] == kind and d["query"]["measures"] == measures and d["query"]["breakdowns"] == grains
    assert (d["query"].get("period") or {}).get("grain") == grain
    assert d["v1_equivalent"] is True and after == visual_after
    assert d["migrated_from"] == {"metric_key": metric, "grains": grains, "period_grain": pg, "visual": visual, "filters": {}, "at": "2026-10-23", "script": "n0116_migrate_definitions"}
    assert (checked.v1.metric_key, sorted(checked.v1.grains), checked.v1.period_grain) == (metric, sorted(grains), pg)


def test_effective_visual_port_matches_web_rules() -> None:
    assert effective_visual_v1("line", ["customer", "product"]) == "hbar"
    assert effective_visual_v1("pie", ["customer"]) == "pie"
    assert effective_visual_v1("pie", ["period"]) == "line"
    assert effective_visual_v1("kpi", []) == "kpi"


# ----------------------------------------------------------------------------- S14 templates


def test_every_starter_widget_plans_with_no_refusals() -> None:
    from app.services.dashboard_templates import TEMPLATES, template_list

    dm, v1 = default_model(), load_catalog()
    assert [t.key for t in TEMPLATES] == ["account_overview", "sellthrough_stock", "cpor_cases"]
    assert TEMPLATES[1].title == "Sell-through & stock across customers"
    measure_ids = {m["id"] for m in _cat()["measures"]}
    for t in TEMPLATES:
        check_dashboard_filters(t.filters_json)
        for w in t.widgets:
            c = check_definition(w.definition(), tenant_id="default")
            assert set(c.definition["query"]["measures"]) <= measure_ids
            # As the dashboard runs it: its window, and (account overview) a customer.
            filters = {"customer": [18]} if "customer" in (t.filters_json.get("required") or []) else {}
            req = request_from_definition(c.definition, period_from="2025-10-23", period_to="2026-10-23")
            req.filters = {**req.filters, **filters}
            plan = plan_request(dm, req, v1_catalog=v1)
            assert plan.measures and not plan.refusals, (t.key, w.title, [r.reason for r in plan.refusals])
            x, y, wd, h = w.layout
            assert 0 <= x and x + wd <= 12 and h > 0
    listing = {t["key"]: t for t in template_list()}
    assert listing["account_overview"]["required_filters"] == ["customer"]
    reasons = [lo["reason"] for lo in listing["account_overview"]["left_out"]]
    assert any(r.startswith("Customer stock cover is not defined for the builder") for r in reasons)
    assert all(lo["reason"] for t in listing.values() for lo in t["left_out"])
    cases = next(t for t in TEMPLATES if t.key == "cpor_cases")
    assert any(w.visual == "table" and "case" in w.breakdowns for w in cases.widgets)
    assert not any(lo["what"] == "A list of cases" for lo in listing["cpor_cases"]["left_out"])


# ----------------------------------------------------------------------------- DB: 0048, script, delivery


def _migration_module():
    path = API_DIR / "alembic" / "versions" / "20261023_0048_dashboard_v2_definitions.py"
    spec = importlib.util.spec_from_file_location("m0048", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _cols(s) -> set[tuple[str, str]]:
    rows = s.execute(text(
        "select table_name, column_name from information_schema.columns where table_name in "
        "('dashboard','dashboard_widget','saved_report') and column_name in ('definition_v2','filters_json','template_key')"
    )).all()
    return {(r[0], r[1]) for r in rows}


def _check(s, name: str) -> str:
    return s.execute(text("select pg_get_constraintdef(oid) from pg_constraint where conname = :n"), {"n": name}).scalar_one()


def test_0048_downgrade_and_upgrade_in_a_rolled_back_transaction() -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.db.session_sync import SessionLocal

    mod = _migration_module()
    s = SessionLocal()
    try:
        if s.execute(text("select current_database()")).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        conn = s.connection()
        assert _cols(s) == {("dashboard", "filters_json"), ("dashboard", "template_key"), ("dashboard_widget", "definition_v2"), ("saved_report", "definition_v2")}
        assert "'pivot'" in _check(s, "ck_dashboard_widget_visual") and "'combo'" in _check(s, "ck_saved_report_visual")
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
        assert _cols(s) == set()
        assert "'pivot'" not in _check(s, "ck_dashboard_widget_visual") and "'donut'" in _check(s, "ck_dashboard_widget_visual")
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        assert len(_cols(s)) == 4
        default = s.execute(text("select column_default, is_nullable from information_schema.columns where table_name='dashboard' and column_name='filters_json'")).one()
        assert default[0].startswith("'{}'") and default[1] == "NO"
    finally:
        s.rollback()
        s.close()


def test_0048_downgrade_refuses_when_a_new_visual_is_used() -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.db.session_sync import SessionLocal

    mod = _migration_module()
    s = SessionLocal()
    try:
        if s.execute(text("select current_database()")).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        did = s.execute(text("insert into dashboard (tenant_id, name) values ('default', 'n0116 downgrade guard') returning id")).scalar_one()
        s.execute(text("insert into dashboard_widget (dashboard_id, tenant_id, title, visual, metric_key) values (:d, 'default', 'combo', 'combo', 'dsi_sellout.units')"), {"d": did})
        with pytest.raises(Exception) as exc:
            with Operations.context(MigrationContext.configure(s.connection())):
                mod.downgrade()
        assert "Downgrade 20261023_0048 refused: 1 dashboard_widget and 0 saved_report rows" in str(exc.value)
    finally:
        s.rollback()
        s.close()


async def _insert_cip_rows(db) -> dict[str, int]:
    from app.models.report_delivery import ReportSchedule
    from app.models.saved_reports import Dashboard, DashboardWidget, SavedReport

    dash = Dashboard(tenant_id="default", name="n0116 Unit 14 canvas", visibility="personal", shared_roles=[])
    db.add(dash)
    await db.flush()
    ids: dict[str, int] = {}
    for tag, metric, grains, pg, visual, *_ in CIP_ROWS:
        if tag.startswith("W"):
            row = DashboardWidget(dashboard_id=dash.id, tenant_id="default", title=tag, visual=visual, metric_key=metric, grains=grains, filters={}, period_grain=pg)
        else:
            row = SavedReport(tenant_id="default", name=tag, visual=visual, metric_key=metric, grains=grains, filters={}, period_grain=pg)
        db.add(row)
        await db.flush()
        ids[tag] = int(row.id)
    db.add(ReportSchedule(tenant_id="default", saved_report_id=ids["R2"], name="n0116 R2 weekly", cadence="weekly_monday_0700", format="xlsx"))
    await db.flush()
    return ids


@pytest.mark.anyio
async def test_migration_script_apply_twice_and_prove_on_cip_test(capsys) -> None:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.saved_reports import DashboardWidget, SavedReport
    from scripts.n0116_migrate_definitions import _counts, _map_and_write, _prove

    clear_query_cache()
    async with AsyncSessionLocal() as db:
        if (await db.execute(text("select current_database()"))).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        try:
            before_any = await _counts(db)
            ids = await _insert_cip_rows(db)
            before = await _counts(db)
            assert before["dashboard_widget"] == before_any["dashboard_widget"] + 6
            v1_before = {
                tag: (r.metric_key, list(r.grains), r.period_grain, dict(r.filters))
                for tag, r in [(f"W{w.id}", w) for w in (await db.execute(select(DashboardWidget))).scalars()]
                + [(f"R{x.id}", x) for x in (await db.execute(select(SavedReport))).scalars()]
            }
            assert await _map_and_write(db, apply=True) == 0
            await db.flush()
            assert await _counts(db) == before
            for tag, metric, grains, pg, visual, kind, measures, grain, visual_after in CIP_ROWS:
                model = DashboardWidget if tag.startswith("W") else SavedReport
                r = await db.get(model, ids[tag])
                d = r.definition_v2
                assert d["kind"] == kind and d["query"]["measures"] == measures and d["v1_equivalent"] is True
                assert r.visual == visual_after and d["migrated_from"]["visual"] == visual
                key = f"{'W' if tag.startswith('W') else 'R'}{r.id}"
                assert (r.metric_key, list(r.grains), r.period_grain, dict(r.filters)) == v1_before[key]  # v1 columns untouched
            capsys.readouterr()
            assert await _map_and_write(db, apply=True) == 0
            assert "rows with definition_v2 IS NULL: 0; written: 0" in capsys.readouterr().out
            assert await _prove(db, "default") == 0
            out = capsys.readouterr().out
            assert "proved rows: 9; total mismatches: 0" in out
        finally:
            await db.rollback()
            clear_query_cache()


@pytest.mark.anyio
async def test_delivery_r2_same_before_and_after_migration_and_v2_only_report_uses_run_v2(monkeypatch) -> None:
    import app.query.model.execute as v2_exec
    import app.services.report_delivery as rd
    from app.db.session import AsyncSessionLocal
    from app.models.saved_reports import SavedReport

    clear_query_cache()
    async with AsyncSessionLocal() as db:
        if (await db.execute(text("select current_database()"))).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        try:
            monkeypatch.setattr(db, "commit", db.flush)
            r2 = SavedReport(tenant_id="default", name="n0116 R2", visual="kpi", metric_key="weeks_of_cover", grains=["distributor", "product"], filters={})
            db.add(r2)
            await db.flush()
            first = await rd.deliver_saved_report(db, report=r2, user=None, skip_cache=True)
            checked, _ = definition_from_v1(metric_key="weeks_of_cover", grains=["distributor", "product"], filters={}, period_grain=None, visual="kpi", tenant_id="default", at="2026-10-23")
            r2.definition_v2 = checked.definition
            await db.flush()
            calls = {"v2": 0}
            real_run_v2 = v2_exec.run_v2

            async def spy(*a, **k):
                calls["v2"] += 1
                return await real_run_v2(*a, **k)

            monkeypatch.setattr(v2_exec, "run_v2", spy)
            second = await rd.deliver_saved_report(db, report=r2, user=None, skip_cache=True)
            assert (second.status, second.value_preview, second.metric_key) == (first.status, first.value_preview, first.metric_key)
            assert calls["v2"] == 0  # v1-equivalent: the v1 path, as schedule 1 runs today

            # A v2-only report: two measures, no v1 equivalent.
            v2c = check_definition({"query": {"measures": ["dsi_sellout.units", "dsi_sellout.lines"]}}, tenant_id="default")
            assert v2c.v1_equivalent is False
            only = SavedReport(tenant_id="default", name="n0116 v2 only", visual="table", metric_key=v2c.v1.metric_key, grains=[], filters={}, definition_v2=v2c.definition)
            db.add(only)
            await db.flush()

            async def no_v1(*a, **k):
                raise AssertionError("v1 engine must not run for a v2-only report")

            monkeypatch.setattr(rd, "execute_query", no_v1)
            expected = await real_run_v2(db, request_from_definition(v2c.definition), tenant_id="default", skip_cache=True)
            row = await rd.deliver_saved_report(db, report=only, user=None, skip_cache=True)
            assert calls["v2"] == 1
            assert row.status == "delivered" and row.metric_key == "dsi_sellout.units"
            total = expected["totals"]["dsi_sellout.units"]
            assert row.value_preview == (str(total) if total is not None else None)
            assert row.data_vintage.get("engine") == "v2"

            # A refused v2-only report fails with the planner's first reason.
            bad = SavedReport(tenant_id="default", name="n0116 v2 refused", visual="kpi", metric_key="dsi_sellout.units_per_week", grains=[], filters={},
                              definition_v2={"v": 1, "kind": "model", "query": {"measures": ["dsi_sellout.units_per_week"], "breakdowns": []}, "v1_equivalent": False})
            db.add(bad)
            await db.flush()
            failed = await rd.deliver_saved_report(db, report=bad, user=None, skip_cache=True)
            assert failed.status == "failed" and "needs period as a breakdown or both period.from and period.to" in (failed.error_message or "")
        finally:
            await db.rollback()
            clear_query_cache()


@pytest.mark.anyio
async def test_governed_filters_honoured_or_refused_at_execute_on_cip_test() -> None:
    from app.db.session import AsyncSessionLocal
    from app.query.model.execute import run_v2

    clear_query_cache()
    async with AsyncSessionLocal() as db:
        if (await db.execute(text("select current_database()"))).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        try:
            # weeks_of_cover + customer: refused, not ignored.
            r = await run_v2(db, V2Request(measures=["weeks_of_cover"], breakdowns=["distributor", "product"], filters={"customer": 1}), tenant_id="default", skip_cache=True)
            assert r["ok"] is False and "cannot be filtered by customer" in r["refusals"][0]["reason"]
            # pipeline_inbound + customer: refused; + bu: applied by the a1 handler.
            r = await run_v2(db, V2Request(measures=["pipeline_inbound"], breakdowns=["period"], filters={"customer": 1}), tenant_id="default", skip_cache=True)
            assert r["ok"] is False
            plain = await run_v2(db, V2Request(measures=["pipeline_inbound"], breakdowns=["period"]), tenant_id="default", skip_cache=True)
            by_bu = await run_v2(db, V2Request(measures=["pipeline_inbound"], breakdowns=["period"], filters={"bu": "n0116-no-such-bu"}), tenant_id="default", skip_cache=True)
            assert plain["ok"] and by_bu["ok"]
            a, b = plain["totals"]["pipeline_inbound"], by_bu["totals"]["pipeline_inbound"]
            # Applied: an unknown business unit leaves nothing (or both are empty on cip_test).
            assert b in (None, 0, 0.0) and (a != b or a in (None, 0, 0.0))
            # support_spend + dates: the a2 handler's own refusal (all-time portfolio).
            r = await run_v2(db, V2Request(measures=["support_spend"], breakdowns=["customer"], period_from="2026-01-01"), tenant_id="default", skip_cache=True)
            assert r["ok"] is False and r["refusals"][0]["reason"].startswith("A2 portfolio intelligence has no period filter today")
        finally:
            await db.rollback()
            clear_query_cache()
