"""GOV-008 independent probe (2026-11-02), N-0116 cross-tenant by-id access through the real API.

Tenant B admin ('other') and tenant A viewer try to read/write tenant A admin's personal objects.
Fictional rolled-back cip_test rows only.
"""
from __future__ import annotations

import json

import pytest

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401

OUT: dict = {}


@pytest.mark.anyio
async def test_cross_tenant_by_id(signed_in):
    from app.main import app  # noqa: F401
    s = signed_in
    A = s.headers["admin"]
    d = (await s.client.post("/api/v1/dashboards", json={"name": "G8 A private"}, headers=A)).json()
    did = d["id"]
    w = (await s.client.post(f"/api/v1/dashboards/{did}/widgets", json={"title": "G8 A widget", "visual": "kpi",
         "definition_v2": {"query": {"measures": ["dsi_sellout.units"]}}}, headers=A)).json()
    wid = w["widgets"][0]["id"]
    rep = (await s.client.post("/api/v1/saved-reports", json={"name": "G8 A report", "metric": "sellout_units",
           "grains": ["customer"], "filters": {}}, headers=A)).json()
    rid = rep["id"]
    sch = await s.client.post("/api/v1/reports/schedules", json={"name": "G8 A sched", "saved_report_id": rid}, headers=A)
    sid = sch.json()["id"]
    dl = (await s.client.post(f"/api/v1/reports/saved/{rid}/deliver", json={}, headers=A)).json()
    B_dash = (await s.client.post("/api/v1/dashboards", json={"name": "G8 B"}, headers=s.headers["other"])).json()
    bid = B_dash["id"]
    calls = [
        ("GET", f"/api/v1/dashboards/{did}", None),
        ("PATCH", f"/api/v1/dashboards/{did}", {"name": "pwned"}),
        ("PATCH", f"/api/v1/dashboards/{did}/layout", [{"id": wid, "x": 0, "y": 0, "w": 1, "h": 1}]),
        ("PUT", f"/api/v1/dashboards/{did}/widgets", {"widgets": []}),
        ("POST", f"/api/v1/dashboards/{did}/widgets", {"title": "x", "visual": "kpi", "metric_key": "sellout_units"}),
        ("PATCH", f"/api/v1/dashboards/{did}/widgets/{wid}", {"title": "pwned"}),
        ("POST", f"/api/v1/dashboards/{did}/widgets/{wid}/promote", {"execution": {"measures": ["dsi_sellout.units"], "breakdowns": []}}),
        ("POST", f"/api/v1/dashboards/{did}/publish", {"shared_roles": []}),
        ("DELETE", f"/api/v1/dashboards/{did}/widgets/{wid}", None),
        ("DELETE", f"/api/v1/dashboards/{did}", None),
        ("PATCH", f"/api/v1/dashboards/{bid}/widgets/{wid}", {"title": "pwned"}),
        ("PATCH", f"/api/v1/dashboards/{bid}/layout", [{"id": wid, "x": 0, "y": 0, "w": 1, "h": 1}]),
        ("DELETE", f"/api/v1/dashboards/{bid}/widgets/{wid}", None),
        ("GET", f"/api/v1/saved-reports/{rid}", None),
        ("PATCH", f"/api/v1/saved-reports/{rid}", {"name": "pwned"}),
        ("POST", f"/api/v1/saved-reports/{rid}/publish", {"shared_roles": []}),
        ("PUT", f"/api/v1/saved-reports/{rid}/overview-pin", None),
        ("DELETE", f"/api/v1/saved-reports/{rid}", None),
        ("GET", f"/api/v1/reports/saved/{rid}/export?format=xlsx", None),
        ("POST", f"/api/v1/reports/saved/{rid}/deliver", {}),
        ("POST", "/api/v1/reports/schedules", {"name": "x", "saved_report_id": rid}),
        ("POST", f"/api/v1/reports/schedules/{sid}/run-now", None),
        ("GET", f"/api/v1/reports/inbox/{dl['id']}/html", None),
        ("POST", "/api/v1/dashboards", {"name": "x", "saved_report_ids": [rid]}),
    ]
    results = {}
    for who in ("other", "viewer"):
        for method, url, body in calls:
            r = await s.client.request(method, url, json=body, headers=s.headers[who])
            results[f"{who} {method} {url.replace(str(did), '{A_dash}').replace(str(wid), '{A_widget}').replace(str(rid), '{A_report}').replace(str(bid), '{B_dash}')}"] = r.status_code
    # Foreign saved_report_id link on own dashboard (no read of the foreign report is attempted).
    r = await s.client.post(f"/api/v1/dashboards/{bid}/widgets", json={"title": "link", "visual": "kpi",
                            "metric_key": "sellout_units", "grains": ["customer"], "saved_report_id": rid}, headers=s.headers["other"])
    link = {"status": r.status_code,
            "saved_report_id_stored": (r.json()["widgets"][0]["saved_report_id"] if r.status_code == 200 else r.text[:200])}
    # Inbox listing for B must not contain A's deliveries.
    inbox_b = (await s.client.get("/api/v1/reports/inbox", headers=s.headers["other"])).json()
    sched_b = (await s.client.get("/api/v1/reports/schedules", headers=s.headers["other"])).json()
    # A objects unchanged.
    a_after = (await s.client.get(f"/api/v1/dashboards/{did}", headers=A)).json()
    rep_after = (await s.client.get(f"/api/v1/saved-reports/{rid}", headers=A)).json()
    # v2 execute (view-rows path) with tenant-A product id from tenant B.
    v2 = (await s.client.post("/api/v1/query/v2/execute", json={"measures": ["dsi_sellout.units"], "breakdowns": ["product"],
          "filters": {"product": [s.products[0].id]}}, headers=s.headers["other"])).json()
    OUT["cross_tenant"] = {
        "status_codes": results,
        "foreign_saved_report_link": link,
        "inbox_b_delivery_ids": [i["id"] for i in inbox_b["items"]], "a_delivery_id": dl["id"],
        "schedules_b": [i["id"] for i in sched_b["items"]], "a_schedule": sid,
        "a_dashboard_after": {"name": a_after.get("name"), "visibility": a_after.get("visibility"),
                              "widgets": [(x["id"], x["title"], x["layout_json"]) for x in a_after.get("widgets", [])]},
        "a_report_after": {"name": rep_after.get("name"), "visibility": rep_after.get("visibility")},
        "v2_b_filtering_a_product": {"ok": v2.get("ok"), "totals": v2.get("totals"), "rows": v2.get("rows")},
    }
    leaks = [k for k, v in results.items() if k.startswith("other") and v < 400]
    OUT["cross_tenant"]["other_success_codes"] = leaks


def teardown_module(module):
    with open(__file__.replace(".py", "_output.json"), "w", encoding="utf-8") as fh:
        json.dump(OUT, fh, indent=1, default=str)
