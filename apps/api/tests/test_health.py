from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_sets_no_store_headers() -> None:
    r = client.get("/health")
    cache = r.headers.get("cache-control", "").lower()
    assert "no-store" in cache or "no-cache" in cache
