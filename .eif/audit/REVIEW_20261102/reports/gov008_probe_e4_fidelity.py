"""GOV-008 independent probe (2026-11-02), E4 saved-query fidelity and S2 migration parity.

Fictional rolled-back cip_test rows only.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401

OUT: dict = {}


async def _many_products(s, n=520):
    from app.api.deps import get_db
    from app.main import app
    from app.models.dimensions import DimCustomer, DimProduct
    from app.models.facts import FactSalesSellout
    factory = asynccontextmanager(app.dependency_overrides[get_db])
    async with factory() as db:
        tid = s.products[0].tenant_id
        customer = (await db.scalars(select(DimCustomer).where(DimCustomer.tenant_id == tid))).one()
        tag = uuid4().hex
        products = [DimProduct(tenant_id=tid, sku=f"g8-{tag}-{i}", name=f"G8 {i}", product_line=s.line_a) for i in range(n)]
        db.add_all(products)
        await db.flush()
        db.add_all([FactSalesSellout(tenant_id=tid, source_key=f"g8-{tag}-{i}", product_id=p.id, customer_id=customer.id,
                                     transaction_date=date(2026, 1, 5), period_start=date(2026, 1, 5), units=1 + i, revenue=0)
                    for i, p in enumerate(products)])
        await db.commit()
    return factory


def _rows(content):
    return list(load_workbook(BytesIO(content))["Data"].values)


@pytest.mark.anyio
async def test_migrated_legacy_report_export_and_delivery_parity(signed_in):
    """S2 / E4 'legacy rows unchanged': the same v1 report before and after the 0048 script mapping."""
    from app.models.saved_reports import SavedReport
    from app.services.dashboard_definitions import definition_from_v1
    s = signed_in
    factory = await _many_products(s)
    headers = s.headers["admin"]
    r = await s.client.post("/api/v1/saved-reports", json={"name": "G8 legacy by product", "metric": "sellout_units",
                                                             "grains": ["product"], "filters": {}, "visual": "table"}, headers=headers)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    before = await s.client.get(f"/api/v1/reports/saved/{rid}/export?format=xlsx", headers=headers)
    deliver_before = (await s.client.post(f"/api/v1/reports/saved/{rid}/deliver", json={}, headers=headers)).json()
    async with factory() as db:
        row = await db.get(SavedReport, rid)
        checked, visual = definition_from_v1(metric_key=row.metric_key, grains=list(row.grains or []), filters=dict(row.filters or {}),
                                             period_grain=row.period_grain, visual=row.visual, tenant_id=row.tenant_id, at="2026-11-02")
        row.definition_v2 = checked.definition  # exactly what scripts/n0116_migrate_definitions.py --apply writes
        await db.commit()
    after = await s.client.get(f"/api/v1/reports/saved/{rid}/export?format=xlsx", headers=headers)
    deliver_after = (await s.client.post(f"/api/v1/reports/saved/{rid}/deliver", json={}, headers=headers)).json()
    b, a = _rows(before.content), _rows(after.content)
    hb, ha = b[0], a[0]
    pid_b, pid_a = hb.index("product_id"), ha.index("product_id")
    OUT["migration_parity"] = {
        "definition": checked.definition,
        "rows_before": len(b) - 1, "rows_after": len(a) - 1,
        "same_order_first_20": [r[pid_b] for r in b[1:21]] == [r[pid_a] for r in a[1:21]],
        "first5_before": b[1:6], "first5_after": a[1:6],
        "value_col_types": sorted({type(r[hb.index('value')]).__name__ for r in b[1:]}),
        "deliver_before_vintage": deliver_before.get("data_vintage"), "deliver_after_vintage": deliver_after.get("data_vintage"),
        "deliver_values": [deliver_before.get("value_preview"), deliver_after.get("value_preview")],
    }


@pytest.mark.anyio
async def test_units_per_week_saved_directly_without_dates(signed_in):
    s = signed_in
    headers = s.headers["admin"]
    out = {}
    r = await s.client.post("/api/v1/saved-reports", json={"name": "G8 rate no dates", "visual": "kpi",
                                                             "definition_v2": {"query": {"measures": ["dsi_sellout.units_per_week"]}}}, headers=headers)
    out["create_status"] = r.status_code
    out["create_body"] = r.json() if r.status_code != 200 else {"definition_v2": r.json().get("definition_v2")}
    if r.status_code == 200:
        rid = r.json()["id"]
        e = await s.client.get(f"/api/v1/reports/saved/{rid}/export?format=xlsx", headers=headers)
        out["export_status"] = e.status_code
        out["export_detail"] = e.json() if e.status_code != 200 else None
        d = await s.client.post(f"/api/v1/reports/saved/{rid}/deliver", json={}, headers=headers)
        out["deliver"] = {k: d.json().get(k) for k in ("status", "error_message", "value_preview", "subject")}
    OUT["units_per_week_direct"] = out


@pytest.mark.anyio
async def test_sorted_limited_card_to_promote_to_saved_xlsx_pdf_delivery(signed_in, monkeypatch):
    """Same rows/order/totals at every hop: card (v2 execute) -> promote -> saved XLSX/PDF -> delivery."""
    from app.api.v1.endpoints import report_exports
    s = signed_in
    headers = s.headers["admin"]
    d = (await s.client.post("/api/v1/dashboards", json={"name": "G8 chain", "filters_json": {"date": {"preset": "custom", "from": "2026-01-01", "to": "2026-02-28"}}}, headers=headers)).json()
    base = f"/api/v1/dashboards/{d['id']}"
    query = {"measures": ["dsi_sellout.units"], "breakdowns": ["product", "period"], "period": {"grain": "month"},
             "sort": {"by": "dsi_sellout.units", "dir": "asc"}, "limit": 2}
    w = (await s.client.post(f"{base}/widgets", json={"title": "G8 asc", "visual": "table", "definition_v2": {"query": query}}, headers=headers)).json()
    wid = w["widgets"][0]["id"]
    card_req = {**query, "period": {"grain": "month", "from": "2026-01-01", "to": "2026-02-28"}}
    card = (await s.client.post("/api/v1/query/v2/execute", json=card_req, headers=headers)).json()
    p = await s.client.post(f"{base}/widgets/{wid}/promote", json={"execution": card_req}, headers=headers)
    assert p.status_code == 200, p.text
    saved = p.json()["saved_report"]
    x = await s.client.get(f"/api/v1/reports/saved/{saved['id']}/export?format=xlsx", headers=headers)
    captured = {}
    real = report_exports.build_pdf_bytes
    monkeypatch.setattr(report_exports, "build_pdf_bytes", lambda **kw: (captured.update(kw), real(**kw))[1])
    pdf = await s.client.get(f"/api/v1/reports/saved/{saved['id']}/export?format=pdf", headers=headers)
    dl = (await s.client.post(f"/api/v1/reports/saved/{saved['id']}/deliver", json={}, headers=headers)).json()
    xr = _rows(x.content)
    hdr = xr[0]
    OUT["chain"] = {
        "saved_definition": saved["definition_v2"],
        "card_rows": [(r.get("product_id"), r.get("bucket_key"), r.get("dsi_sellout.units")) for r in card["rows"]],
        "card_total": card["totals"], "card_truncated": card.get("truncated"),
        "xlsx_rows": [(r[hdr.index("product_id")], r[hdr.index("bucket_key")] if "bucket_key" in hdr else None, r[hdr.index("dsi_sellout.units")]) for r in xr[1:]],
        "xlsx_header": hdr,
        "pdf_status": pdf.status_code,
        "pdf_rows": [(r.get("product_id"), r.get("bucket_key"), r.get("dsi_sellout.units")) for r in captured.get("rows") or []],
        "pdf_value": captured.get("value"),
        "delivery": {k: dl.get(k) for k in ("value_preview", "data_vintage", "status")},
    }
    assert OUT["chain"]["card_rows"] == OUT["chain"]["xlsx_rows"] == OUT["chain"]["pdf_rows"]


@pytest.mark.anyio
async def test_promotion_without_execution_body_on_relative_dashboard(signed_in):
    """Old client / API caller omits execution on a dated dashboard: refused, or silently all-time?"""
    s = signed_in
    headers = s.headers["admin"]
    out = {}
    for name, filters in [("relative", {"date": {"preset": "last_13_weeks"}}), ("no_bar", {}),
                          ("customer_only", {"customer": [1]})]:
        d = (await s.client.post("/api/v1/dashboards", json={"name": f"G8 {name}", "filters_json": filters}, headers=headers)).json()
        base = f"/api/v1/dashboards/{d['id']}"
        w = (await s.client.post(f"{base}/widgets", json={"title": "G8 units", "visual": "kpi",
                                                          "definition_v2": {"query": {"measures": ["dsi_sellout.units"]}}}, headers=headers)).json()
        r = await s.client.post(f"{base}/widgets/{w['widgets'][0]['id']}/promote", headers=headers)
        out[name] = [r.status_code, (r.json().get("detail") if r.status_code != 200 else r.json()["saved_report"]["definition_v2"])]
    OUT["promote_no_execution"] = out


@pytest.mark.anyio
async def test_saved_v2_patch_with_v1_fields_drops_definition(signed_in):
    """API-level read-only check: does a PATCH with v1 fields silently discard a v2 definition?"""
    s = signed_in
    headers = s.headers["admin"]
    r = await s.client.post("/api/v1/saved-reports", json={"name": "G8 v2", "visual": "table",
        "definition_v2": {"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["product"], "limit": 1, "sort": {"dir": "asc"}}}}, headers=headers)
    rid = r.json()["id"]
    p = await s.client.patch(f"/api/v1/saved-reports/{rid}", json={"grains": ["customer"]}, headers=headers)
    OUT["v2_patch_v1_fields"] = {"status": p.status_code, "definition_v2_after": p.json().get("definition_v2") if p.status_code == 200 else p.json(),
                                 "metric_after": p.json().get("metric_key") if p.status_code == 200 else None}


def teardown_module(module):
    with open(__file__.replace(".py", "_output.json"), "w", encoding="utf-8") as fh:
        json.dump(OUT, fh, indent=1, default=str)
