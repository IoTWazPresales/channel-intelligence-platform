from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body.get("service") == "cip-api"


def test_health_sets_no_store_headers() -> None:
    r = client.get("/health")
    cache = r.headers.get("cache-control", "").lower()
    assert "no-store" in cache or "no-cache" in cache


def test_health_ready_returns_ready_or_503() -> None:
    r = client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["status"] in ("ready", "not_ready")
    if r.status_code == 200:
        assert body.get("ok") is True
        assert body.get("database")
