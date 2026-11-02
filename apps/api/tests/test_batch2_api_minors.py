"""GOV-008 review 2 Nov, batch-2 minors through the API: widget report reference, report without dates, port code, NaN body.

Real auth and SQL on cip_test; every row rolls back with the fixture (fictional data).
"""

from __future__ import annotations

import json

import pytest

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401
from tests.test_report_schedule_recipient_scope import scheduled  # noqa: F401

WIDGET = {"title": "W", "visual": "table", "definition_v2": {"query": {"measures": ["dsi_sellout.units"]}}}


async def _dashboard(client, admin):
    r = await client.post("/api/v1/dashboards", json={"name": "Batch 2 widget reference"}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.anyio
async def test_widget_rejects_another_tenants_saved_report_id_on_every_write_path(scheduled):
    s = scheduled
    client, admin = s.auth.client, s.auth.headers["admin"]
    mine, theirs = s.reports[0].id, s.reports[1].id  # reports[1] belongs to tenant B
    did = await _dashboard(client, admin)
    base = f"/api/v1/dashboards/{did}"

    r = await client.post(f"{base}/widgets", json={**WIDGET, "saved_report_id": theirs}, headers=admin)
    assert r.status_code == 400 and "not found in tenant" in r.text  # before: 200 and stored
    r = await client.post("/api/v1/dashboards", json={"name": "X", "widgets": [{**WIDGET, "saved_report_id": theirs}]}, headers=admin)
    assert r.status_code == 400
    r = await client.put(f"{base}/widgets", json={"widgets": [{**WIDGET, "saved_report_id": theirs}]}, headers=admin)
    assert r.status_code == 400

    ghost = 2_000_000_000  # the review's stored 987: an id that exists nowhere (an id-existence gap, not a leak)
    r = await client.post(f"{base}/widgets", json={**WIDGET, "saved_report_id": ghost}, headers=admin)
    assert r.status_code == 400 and "not found in tenant" in r.text  # before: 200, stored
    r = await client.put(f"{base}/widgets", json={"widgets": [{**WIDGET, "saved_report_id": ghost}]}, headers=admin)
    assert r.status_code == 400
    r = await client.post("/api/v1/dashboards", json={"name": "X", "widgets": [{**WIDGET, "saved_report_id": ghost}]}, headers=admin)
    assert r.status_code == 400

    r = await client.post(f"{base}/widgets", json={**WIDGET, "saved_report_id": mine}, headers=admin)  # control: own tenant
    assert r.status_code == 200, r.text
    assert any(w["saved_report_id"] == mine for w in r.json()["widgets"])
    # Nothing of tenant B was stored on the dashboard.
    after = (await client.get(base, headers=admin)).json()
    assert all(w["saved_report_id"] != theirs for w in after["widgets"])


@pytest.mark.anyio
async def test_a_per_week_report_without_dates_is_refused_at_a_direct_post(signed_in):
    client, admin = signed_in.client, signed_in.headers["admin"]
    undated = {"query": {"measures": ["dsi_sellout.units_per_week"], "breakdowns": ["customer"]}}
    r = await client.post("/api/v1/saved-reports", json={"name": "Per week, no dates", "visual": "table", "definition_v2": undated}, headers=admin)
    assert r.status_code == 400 and "needs execution dates" in r.text  # before: stored, then every export returned 400

    dated = {**undated, "dashboard": {"fixed_window": {"from": "2026-01-01", "to": "2026-03-31"}}}
    r = await client.post("/api/v1/saved-reports", json={"name": "Per week, fixed window", "visual": "table", "definition_v2": dated}, headers=admin)
    assert r.status_code == 200, r.text  # control: a fixed window is a date range
    rid = r.json()["id"]
    r = await client.patch(f"/api/v1/saved-reports/{rid}", json={"definition_v2": undated}, headers=admin)
    assert r.status_code == 400 and "needs execution dates" in r.text  # the same rule on update


@pytest.mark.anyio
async def test_port_code_must_be_a_five_character_locode(signed_in):
    client, admin = signed_in.client, signed_in.headers["admin"]
    for bad in ("XXX", "ABC", "Z1DUR", "ZA DUR!"):
        r = await client.post("/api/v1/shipping/port-conditions", json={"port_code": bad, "delay_days": 3}, headers=admin)
        assert r.status_code == 422, (bad, r.status_code, r.text)
    r = await client.post("/api/v1/shipping/port-conditions", json={"port_code": " zadur ", "delay_days": 3}, headers=admin)
    assert r.status_code == 201 and r.json()["port_code"] == "ZADUR"


@pytest.mark.anyio
async def test_a_raw_nan_body_is_a_422_not_a_500(signed_in):
    client, admin = signed_in.client, signed_in.headers["admin"]
    headers = {**admin, "content-type": "application/json"}
    for literal in (b"NaN", b"Infinity", b"-Infinity"):
        body = b'{"port_code": "ZADUR", "delay_days": ' + literal + b"}"
        r = await client.post("/api/v1/shipping/port-conditions", content=body, headers=headers)
        assert r.status_code == 422, (literal, r.status_code)
        assert json.loads(r.content)["detail"][0]["loc"][-1] == "delay_days"
