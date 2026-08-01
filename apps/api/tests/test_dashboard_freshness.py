"""Dashboard summary freshness shape (P2-4)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dashboard_summary_includes_freshness() -> None:
    r = client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert "freshness" in body
    fresh = body["freshness"]
    assert "tenant_id" in fresh
    assert "is_stale" in fresh
    assert "by_template" in fresh
    assert isinstance(fresh["by_template"], list)
    assert "failed_import_jobs" in body["kpis"]
