"""N-0116 HTTP: widgets and saved reports with definition_v2, PATCH /layout, filters_json,
starters (GET /dashboards/templates, POST /dashboards/from-template), promote.

Runs through the real app on cip_test. The request session is bound to one connection whose outer
transaction is rolled back at the end (app commits become savepoint releases), so nothing persists.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.main import app
from app.query.cache import clear_query_cache
from app.semantics.registry import clear_catalog_cache

V2_UNITS_WEEK = {"v": 1, "query": {"measures": ["dsi_sellout.units"], "breakdowns": ["period"], "period": {"grain": "week"}}}
V2_ONLY = {"v": 1, "query": {"measures": ["dsi_sellout.units", "dsi_sellout.lines"], "breakdowns": ["bu"], "sort": {"by": "dsi_sellout.units", "dir": "desc"}, "limit": 50},
           "display": {"top_n": 15, "series": {"dsi_sellout.lines": {"kind": "line", "axis": "right"}}}}


@pytest.fixture()
async def tx():
    from app.db.session import engine

    clear_catalog_cache()
    clear_query_cache()
    async with engine.connect() as conn:
        outer = await conn.begin()
        if (await conn.execute(text("select current_database()"))).scalar_one() != "cip_test":
            await outer.rollback()
            pytest.skip("cip_test only")
        # One session per request (as get_db), all on this connection inside the outer transaction.
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

        async def _db():
            s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
            try:
                yield s
            finally:
                await s.close()

        app.dependency_overrides[get_db] = _db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield client, session
        finally:
            app.dependency_overrides.pop(get_db, None)
            await session.close()
            await outer.rollback()
            clear_query_cache()


async def _user(session: AsyncSession, email: str, role: str = "viewer") -> int:
    uid = (
        await session.execute(
            text(
                "insert into app_user (tenant_id, email, password_hash, display_name, role) "
                "values ('default', :e, 'x', :e, :r) returning id"
            ),
            {"e": email, "r": role},
        )
    ).scalar_one()
    return int(uid)


def _h(uid: int) -> dict[str, str]:
    return {"X-User-Id": str(uid)}


async def _dashboard(client, uid: int, **extra) -> dict:
    r = await client.post("/api/v1/dashboards", json={"name": "n0116 api", **extra}, headers=_h(uid))
    assert r.status_code == 200, r.text
    return r.json()


async def _widget_count(session: AsyncSession, dashboard_id: int) -> int:
    return int((await session.execute(text("select count(*) from dashboard_widget where dashboard_id = :d"), {"d": dashboard_id})).scalar_one())


@pytest.mark.anyio
async def test_widget_post_and_patch_with_definition_v2(tx) -> None:
    client, session = tx
    uid = await _user(session, "n0116.owner@local")
    d = await _dashboard(client, uid)
    base = f"/api/v1/dashboards/{d['id']}/widgets"

    # Valid v2, v1-equivalent: stored with the v1 columns mirrored.
    r = await client.post(base, json={"title": "Units by week", "visual": "line", "definition_v2": V2_UNITS_WEEK}, headers=_h(uid))
    assert r.status_code == 200, r.text
    w = r.json()["widgets"][0]
    assert w["definition_v2"]["kind"] == "model" and w["definition_v2"]["v1_equivalent"] is True
    assert (w["metric_key"], w["grains"], w["period_grain"]) == ("sellout_units", ["period"], "week")

    # Valid v2-only with a new visual: v1 columns are the fallback mirror.
    r = await client.post(base, json={"title": "Units and lines by BU", "visual": "combo", "definition_v2": V2_ONLY}, headers=_h(uid))
    assert r.status_code == 200, r.text
    w2 = next(x for x in r.json()["widgets"] if x["title"] == "Units and lines by BU")
    assert w2["visual"] == "combo" and w2["definition_v2"]["v1_equivalent"] is False
    assert (w2["metric_key"], w2["grains"], w2["period_grain"], w2["filters"]) == ("dsi_sellout.units", [], None, {})
    assert w2["definition_v2"]["display"]["series"]["dsi_sellout.lines"]["axis"] == "right"

    # Refused: cross-model, wall, limit 5,001 -> 400 with the planner's text, nothing written.
    n = await _widget_count(session, d["id"])
    for bad, needle in (
        ({"v": 1, "query": {"measures": ["dsi_sellout.units", "cst_sellthrough.units"]}}, "One query reads one model"),
        ({"v": 1, "query": {"measures": ["cst_sellthrough.units"], "filters": {"distributor": [1]}}}, "do not say which distributor supplied the stock"),
        ({"v": 1, "query": {"measures": ["dsi_sellout.units"], "limit": 5001}}, "limit 5001 is above the maximum of 5000 rows"),
    ):
        r = await client.post(base, json={"title": "bad", "definition_v2": bad}, headers=_h(uid))
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert needle in detail["message"] and needle in detail["refusals"][0]["reason"]
        assert await _widget_count(session, d["id"]) == n

    # A v1 body is still accepted unchanged (definition_v2 stays null).
    r = await client.post(base, json={"title": "v1", "visual": "line", "metric_key": "sellout_units", "grains": ["period"], "period_grain": "week"}, headers=_h(uid))
    assert r.status_code == 200, r.text
    v1w = next(x for x in r.json()["widgets"] if x["title"] == "v1")
    assert v1w["definition_v2"] is None
    # Neither metric_key nor definition_v2 -> 400.
    r = await client.post(base, json={"title": "empty"}, headers=_h(uid))
    assert r.status_code == 400

    # PATCH title only on a v2-only widget keeps its definition (no v1 re-validation).
    r = await client.patch(f"{base}/{w2['id']}", json={"title": "Renamed"}, headers=_h(uid))
    assert r.status_code == 200, r.text
    got = next(x for x in r.json()["widgets"] if x["id"] == w2["id"])
    assert got["title"] == "Renamed" and got["definition_v2"] == w2["definition_v2"]

    # PATCH with a refused definition -> 400 and the stored one is unchanged.
    r = await client.patch(f"{base}/{w2['id']}", json={"definition_v2": {"v": 1, "query": {"measures": ["dsi_sellout.units"], "breakdowns": ["site_label"]}}}, headers=_h(uid))
    assert r.status_code == 400
    r = await client.get(f"/api/v1/dashboards/{d['id']}", headers=_h(uid))
    assert next(x for x in r.json()["widgets"] if x["id"] == w2["id"])["definition_v2"] == w2["definition_v2"]

    # PATCH with a new definition replaces it.
    r = await client.patch(f"{base}/{w2['id']}", json={"definition_v2": V2_UNITS_WEEK, "visual": "line"}, headers=_h(uid))
    assert r.status_code == 200
    got = next(x for x in r.json()["widgets"] if x["id"] == w2["id"])
    assert got["definition_v2"]["query"]["measures"] == ["dsi_sellout.units"] and got["metric_key"] == "sellout_units"

    # PATCH definition_v2 null: back to v1 (its mirror is v1-valid).
    r = await client.patch(f"{base}/{w['id']}", json={"definition_v2": None}, headers=_h(uid))
    assert r.status_code == 200
    got = next(x for x in r.json()["widgets"] if x["id"] == w["id"])
    assert got["definition_v2"] is None and got["metric_key"] == "sellout_units"


@pytest.mark.anyio
async def test_patch_layout_writes_only_layout_and_put_keeps_definition(tx) -> None:
    client, session = tx
    uid = await _user(session, "n0116.layout@local")
    d = await _dashboard(client, uid)
    base = f"/api/v1/dashboards/{d['id']}"
    r = await client.post(f"{base}/widgets", json={"title": "A", "visual": "combo", "definition_v2": V2_ONLY}, headers=_h(uid))
    r = await client.post(f"{base}/widgets", json={"title": "B", "visual": "line", "definition_v2": V2_UNITS_WEEK}, headers=_h(uid))
    widgets = {x["title"]: x for x in r.json()["widgets"]}
    a, b = widgets["A"], widgets["B"]

    # Only A in the body: B is not deleted and keeps its layout; A keeps definition_v2.
    r = await client.patch(f"{base}/layout", json=[{"id": a["id"], "x": 6, "y": 16, "w": 6, "h": 9}], headers=_h(uid))
    assert r.status_code == 200, r.text
    after = {x["id"]: x for x in r.json()["widgets"]}
    assert set(after) == {a["id"], b["id"]}
    assert after[a["id"]]["layout_json"] == {"x": 6, "y": 16, "w": 6, "h": 9}
    assert after[b["id"]]["layout_json"] == b["layout_json"]
    for key in ("definition_v2", "title", "visual", "metric_key", "grains", "filters", "period_grain", "updated_at"):
        assert after[a["id"]][key] == a[key], key

    # Unknown or duplicate ids: 400, nothing written.
    for body in ([{"id": a["id"], "x": 0, "y": 0, "w": 3, "h": 3}, {"id": 999999999, "x": 0, "y": 0, "w": 3, "h": 3}],
                 [{"id": a["id"], "x": 0, "y": 0, "w": 3, "h": 3}, {"id": a["id"], "x": 1, "y": 0, "w": 3, "h": 3}]):
        r = await client.patch(f"{base}/layout", json=body, headers=_h(uid))
        assert r.status_code == 400
    r = await client.get(base, headers=_h(uid))
    assert next(x for x in r.json()["widgets"] if x["id"] == a["id"])["layout_json"] == {"x": 6, "y": 16, "w": 6, "h": 9}
    # w above 12 -> 422.
    r = await client.patch(f"{base}/layout", json=[{"id": a["id"], "x": 0, "y": 0, "w": 13, "h": 3}], headers=_h(uid))
    assert r.status_code == 422

    # Another user cannot move it.
    other = await _user(session, "n0116.other@local")
    r = await client.patch(f"{base}/layout", json=[{"id": a["id"], "x": 0, "y": 0, "w": 3, "h": 3}], headers=_h(other))
    assert r.status_code == 403

    # The old PUT (today's client) sending the mirrored v1 fields keeps a v2-only widget's definition.
    cur = {x["id"]: x for x in (await client.get(base, headers=_h(uid))).json()["widgets"]}
    body = {"widgets": [{k: cur[i][k] for k in ("id", "title", "visual", "metric_key", "grains", "filters", "period_grain", "layout_json", "sort_order")} for i in cur]}
    r = await client.put(f"{base}/widgets", json=body, headers=_h(uid))
    assert r.status_code == 200, r.text
    assert {x["id"]: x["definition_v2"] for x in r.json()["widgets"]} == {i: cur[i]["definition_v2"] for i in cur}


@pytest.mark.anyio
async def test_dashboard_filters_json_round_trip(tx) -> None:
    client, session = tx
    uid = await _user(session, "n0116.filters@local")
    d = await _dashboard(client, uid)
    assert d["filters_json"] == {} and d["template_key"] is None
    f = {"date": {"preset": "last_13_weeks", "from": None, "to": None}, "compare": "previous_year", "customer": [18, 299], "bu": ["Notebook"], "required": []}
    r = await client.patch(f"/api/v1/dashboards/{d['id']}", json={"filters_json": f}, headers=_h(uid))
    assert r.status_code == 200, r.text
    assert r.json()["filters_json"] == f
    r = await client.get(f"/api/v1/dashboards/{d['id']}", headers=_h(uid))
    assert r.json()["filters_json"] == f
    r = await client.patch(f"/api/v1/dashboards/{d['id']}", json={"filters_json": {"compare": "yesterday"}}, headers=_h(uid))
    assert r.status_code == 400
    assert (await client.get(f"/api/v1/dashboards/{d['id']}", headers=_h(uid))).json()["filters_json"] == f
    # Other fields leave filters_json alone.
    r = await client.patch(f"/api/v1/dashboards/{d['id']}", json={"name": "renamed"}, headers=_h(uid))
    assert r.json()["filters_json"] == f


@pytest.mark.anyio
async def test_from_template_makes_three_personal_dashboards_every_widget_planner_clean(tx) -> None:
    from app.query.model.graph import plan_request
    from app.query.model.loader import default_model
    from app.semantics.registry import load_catalog
    from app.services.dashboard_definitions import request_from_definition

    client, session = tx
    uid = await _user(session, "n0116.starter@local")
    other = await _user(session, "n0116.starter.other@local")
    r = await client.get("/api/v1/dashboards/templates", headers=_h(uid))
    assert r.status_code == 200
    listing = {t["key"]: t for t in r.json()["items"]}
    assert list(listing) == ["account_overview", "sellthrough_stock", "cpor_cases"]
    assert listing["sellthrough_stock"]["title"] == "Sell-through & stock across customers"

    dm, v1 = default_model(), load_catalog()
    sizes = {"account_overview": 8, "sellthrough_stock": 6, "cpor_cases": 8}
    for key, n in sizes.items():
        r = await client.post("/api/v1/dashboards/from-template", json={"key": key}, headers=_h(uid))
        assert r.status_code == 200, r.text
        dash = r.json()
        assert dash["template_key"] == key and dash["visibility"] == "personal" and dash["owner_user_id"] == uid
        assert dash["filters_json"] == listing[key]["filters_json"]
        assert len(dash["widgets"]) == n
        for w in dash["widgets"]:
            req = request_from_definition(w["definition_v2"], period_from="2025-10-23", period_to="2026-10-23")
            if key == "account_overview":
                req.filters = {"customer": [18]}
            plan = plan_request(dm, req, v1_catalog=v1)
            assert plan.measures and not plan.refusals, (key, w["title"])
            assert set(w["layout_json"]) == {"x", "y", "w", "h"}
        # Personal to the creator.
        assert (await client.get(f"/api/v1/dashboards/{dash['id']}", headers=_h(other))).status_code == 403
    assert listing["account_overview"]["filters_json"]["required"] == ["customer"]
    r = await client.post("/api/v1/dashboards/from-template", json={"key": "nope"}, headers=_h(uid))
    assert r.status_code == 404


@pytest.mark.anyio
async def test_promote_copies_definition_and_saved_report_accepts_definition_v2(tx) -> None:
    client, session = tx
    uid = await _user(session, "n0116.promote@local")
    d = await _dashboard(client, uid)
    r = await client.post(f"/api/v1/dashboards/{d['id']}/widgets", json={"title": "V2 only", "visual": "table", "definition_v2": V2_ONLY}, headers=_h(uid))
    w = r.json()["widgets"][0]
    r = await client.post(f"/api/v1/dashboards/{d['id']}/widgets/{w['id']}/promote", headers=_h(uid))
    assert r.status_code == 200, r.text
    rep = r.json()["saved_report"]
    assert rep["definition_v2"] == w["definition_v2"] and rep["metric_key"] == "dsi_sellout.units" and rep["visual"] == "table"

    # Saved report create / patch with definition_v2.
    r = await client.post("/api/v1/saved-reports", json={"name": "n0116 v2 report", "visual": "pivot", "definition_v2": V2_ONLY}, headers=_h(uid))
    assert r.status_code == 200, r.text
    sr = r.json()
    assert sr["visual"] == "pivot" and sr["definition_v2"]["v1_equivalent"] is False
    r = await client.post("/api/v1/saved-reports", json={"name": "bad", "definition_v2": {"v": 1, "query": {"measures": ["cst_sellthrough.units"], "filters": {"distributor": [1]}}}}, headers=_h(uid))
    assert r.status_code == 400 and "do not say which distributor" in r.json()["detail"]["message"]
    r = await client.patch(f"/api/v1/saved-reports/{sr['id']}", json={"name": "renamed"}, headers=_h(uid))
    assert r.status_code == 200 and r.json()["definition_v2"] == sr["definition_v2"]
    r = await client.patch(f"/api/v1/saved-reports/{sr['id']}", json={"definition_v2": V2_UNITS_WEEK}, headers=_h(uid))
    assert r.status_code == 200
    assert (r.json()["metric_key"], r.json()["grains"], r.json()["period_grain"]) == ("sellout_units", ["period"], "week")
    # v1 body still accepted.
    r = await client.post("/api/v1/saved-reports", json={"name": "v1", "metric": "sellout_units", "grains": ["period"], "period_grain": "week"}, headers=_h(uid))
    assert r.status_code == 200 and r.json()["definition_v2"] is None
    # Back to v1 explicitly on a report whose mirror is v1-valid.
    r = await client.patch(f"/api/v1/saved-reports/{sr['id']}", json={"definition_v2": None}, headers=_h(uid))
    assert r.status_code == 200 and r.json()["definition_v2"] is None and r.json()["metric_key"] == "sellout_units"


@pytest.mark.anyio
async def test_starter_routes_refuse_anonymous_callers(monkeypatch) -> None:
    monkeypatch.setenv("CIP_AUTH_MODE", "session")
    get_settings.cache_clear()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/dashboards/templates")).status_code == 401
            assert (await client.post("/api/v1/dashboards/from-template", json={"key": "cpor_cases"})).status_code == 401
            assert (await client.patch("/api/v1/dashboards/1/layout", json=[])).status_code == 401
    finally:
        get_settings.cache_clear()


def test_new_routes_registered_before_the_id_route() -> None:
    paths = [getattr(r, "path", "") for r in app.routes]
    assert paths.index("/api/v1/dashboards/templates") < paths.index("/api/v1/dashboards/{dashboard_id}")
    assert "/api/v1/dashboards/{dashboard_id}/layout" in paths and "/api/v1/dashboards/from-template" in paths
