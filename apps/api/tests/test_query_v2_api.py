"""N-0115 v2 endpoints: signed-in only, catalog shape, explain without running, execute.

- anonymous calls get 401 in session mode (each v2 route depends on get_current_user itself,
  besides the router gate);
- GET /semantics/v2/catalog lists base, calculated and governed measures, breakdowns, walls;
- POST /query/v2/explain validates and returns SQL with parameter names, never values;
- POST /query/v2/execute answers on cip_test through the real app (router scope binding).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.query.cache import clear_query_cache


@pytest.fixture()
def session_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CIP_AUTH_MODE", "session")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_v2_routes_refuse_anonymous_callers(session_mode) -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/semantics/v2/catalog").status_code == 401
        body = {"measures": ["dsi_sellout.units"], "breakdowns": ["period"]}
        assert client.post("/api/v1/query/v2/execute", json=body).status_code == 401
        assert client.post("/api/v1/query/v2/explain", json=body).status_code == 401
        forged = {"X-User-Role": "admin", "X-User-Id": "1"}
        assert client.post("/api/v1/query/v2/execute", json=body, headers=forged).status_code == 401


def test_v2_routes_carry_get_current_user_explicitly() -> None:
    from app.core.security import get_current_user

    wanted = {"/api/v1/semantics/v2/catalog", "/api/v1/query/v2/execute", "/api/v1/query/v2/explain"}
    found = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path in wanted:
            deps = [d.call for d in route.dependant.dependencies]
            assert get_current_user in deps, path
            found.add(path)
    assert found == wanted


def test_catalog_v2_shape() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/semantics/v2/catalog")
    assert r.status_code == 200
    cat = r.json()
    by_id = {m["id"]: m for m in cat["measures"]}
    units = by_id["dsi_sellout.units"]
    assert units["kind"] == "base" and units["unit"] == "units" and units["additivity"] == "additive"
    assert units["legacy_key"] == "sellout_units" and units["model"] == "dsi_sellout"
    assert "region" in units["breakdowns"] and "site_label" not in units["breakdowns"]
    assert units["period_grains"] == ["week", "month", "quarter", "year"]
    assert by_id["cst_sellthrough.reported_soh"]["additivity"] == "semi_additive"
    assert "period" not in by_id["cst_sellthrough.reported_soh"]["breakdowns"]
    assert by_id["cpor.delivery_rate"]["kind"] == "calculated" and by_id["cpor.delivery_rate"]["calc"] == "ratio"
    assert by_id["dsi_sellout.units_pct_change"]["requires"] == ["period"]
    woc = by_id["weeks_of_cover"]
    assert woc["kind"] == "governed" and woc["grain_sets"] == [["distributor", "product"]]
    assert "sellout_units" not in by_id  # answered by dsi_sellout.units in v2
    assert {w["id"] for w in cat["walls"]} >= {"W-SITE-CST-ONLY", "W-CUSTOMER-ROLE", "W-CST-NO-DISTRIBUTOR"}
    assert all(w["reason"] for w in cat["walls"])
    groups = {b["id"]: b["group"] for b in cat["breakdowns"]}
    assert groups["site_label"] == "Store" and groups["bu"] == "Product" and groups["region"] == "Customer"
    assert any(p["id"] == "cpor.open_cases" for p in cat["pending"])


def test_explain_validates_and_shows_parameter_names_only() -> None:
    body = {
        "measures": ["dsi_sellout.units", "dsi_sellout.units_per_week"],
        "breakdowns": ["customer"],
        "filters": {"bu": ["NB' OR '1'='1"]},
        "period": {"from": "2026-01-01", "to": "2026-03-31"},
    }
    with TestClient(app) as client:
        r = client.post("/api/v1/query/v2/explain", json=body)
        bad = client.post("/api/v1/query/v2/explain", json={"measures": ["dsi_sellout.units"], "breakdowns": ["site_label"]})
        over = client.post("/api/v1/query/v2/explain", json={"measures": ["dsi_sellout.units"], "limit": 5001})
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is True and out["rows"] == []
    ex = out["explain"]
    assert ex["models"] == ["dsi_sellout"] and ex["filters"] == [{"breakdown": "bu", "values": 1}]
    assert "OR '1'='1" not in ex["sql"] and "2026-01-01" not in ex["sql"] and "%(period_from)s" in ex["sql"]
    assert "W-SITE-CST-ONLY" in ex["walls_checked"]
    assert bad.json()["ok"] is False
    assert bad.json()["refusals"][0]["reason"] == "site_label is CST-only. DSI sell-out does not have a site grain."
    assert over.json()["ok"] is False and "not clamped" in over.json()["refusals"][0]["reason"]


def test_execute_runs_on_the_request_session() -> None:
    clear_query_cache()
    body = {"measures": ["dsi_sellout.units", "dsi_sellout.lines"], "breakdowns": ["period"], "period": {"grain": "month"}}
    with TestClient(app) as client:
        first = client.post("/api/v1/query/v2/execute", json=body)
        second = client.post("/api/v1/query/v2/execute", json=body)
        v1 = client.post("/api/v1/query/execute", json={"metric": "sellout_units", "grains": ["period"], "period_grain": "month"})
    clear_query_cache()
    assert first.status_code == 200, first.text
    out = first.json()
    assert out["ok"] is True and out["cache"]["hit"] is False and second.json()["cache"]["hit"] is True
    assert out["explain"]["scope"]["source"] == "this transaction"
    assert out["explain"]["scope"]["product_lines"] == "*"  # stub admin: every line
    assert {c["id"] for c in out["columns"]} == {"period", "dsi_sellout.units", "dsi_sellout.lines"}
    # Same figures as v1 for the same request (v1 untouched).
    old = v1.json()
    assert old["ok"] is True
    assert round(out["totals"]["dsi_sellout.units"], 6) == round(old["value"], 6)
    assert [r["bucket_key"] for r in out["rows"]] == [p["bucket_key"] for p in old["series"]]
