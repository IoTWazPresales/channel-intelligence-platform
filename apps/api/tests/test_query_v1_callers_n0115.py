"""N-0115: every v1 caller of the query engine still answers through today's handlers.

v2 (the model compiler) is additive. These tests pin the v1 paths that existing tests did not
already exercise end to end (the rest are listed in the N-0115 report):

- POST /query/explain (HTTP) - planned handler, no SQL;
- POST /semantics/validate (HTTP) - v1 refusal text;
- POST /saved-reports (HTTP) - invalid grain refused with the v1 text before any write;
- POST /reports/export (HTTP) - xlsx built from the v1 engine result;
- services.report_delivery.deliver_saved_report - v1 engine value lands on the delivery row
  (cip_test, one rolled-back transaction; commit replaced by flush).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.main import app
from app.query.cache import clear_query_cache


def test_v1_query_explain_endpoint_unchanged() -> None:
    with TestClient(app) as client:
        r = client.post("/api/v1/query/explain", json={"metric": "sellout_units", "grains": ["period"], "period_grain": "week"})
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is True and out["handler"] == "volume_series" and out["period_grain"] == "week"
    assert "explain" in out and "engine" not in (out.get("explain") or {})


def test_v1_semantics_validate_endpoint_unchanged() -> None:
    with TestClient(app) as client:
        r = client.post("/api/v1/semantics/validate", json={"metric": "weeks_of_cover", "grains": ["period", "bu"]})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["message"] == "Weeks of cover is only meaningful at distributor × product (A3 grain lock)."


def test_v1_saved_report_create_validates_with_v1_text() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/saved-reports",
            json={"name": "n0115 refused", "metric": "sellout_units", "grains": ["site_label"]},
        )
    assert r.status_code == 400
    assert r.json()["detail"]["message"] == "site_label is CST-only. DSI sell-out does not have a site grain."


def test_v1_report_export_unchanged() -> None:
    clear_query_cache()
    with TestClient(app) as client:
        r = client.post("/api/v1/reports/export", json={"metric": "sellout_units", "grains": ["period"], "format": "xlsx"})
    clear_query_cache()
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"  # xlsx is a zip


@pytest.mark.anyio
async def test_v1_report_delivery_unchanged(monkeypatch) -> None:
    from app.models.saved_reports import SavedReport
    from app.query.engine import execute_query
    from app.services.report_delivery import deliver_saved_report

    clear_query_cache()
    async with AsyncSessionLocal() as db:
        if (await db.execute(text("select current_database()"))).scalar_one() != "cip_test":
            pytest.skip("cip_test only")
        try:
            report = SavedReport(tenant_id="default", name="n0115 delivery", metric_key="sellout_units", grains=["period"], filters={})
            db.add(report)
            await db.flush()
            expected = await execute_query(db, metric="sellout_units", grains=["period"], tenant_id="default", skip_cache=True)
            monkeypatch.setattr(db, "commit", db.flush)
            row = await deliver_saved_report(db, report=report, user=None, skip_cache=True)
            assert row.status == "delivered" and row.metric_key == "sellout_units"
            assert row.value_preview == str(expected.value)
        finally:
            await db.rollback()
            clear_query_cache()
