from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_openapi_lists_core_paths() -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = spec.get("paths", {})
    assert "/health" in paths
    assert any(p.startswith("/api/v1/") for p in paths)
    assert "/api/v1/products/references" in paths
    assert "/api/v1/dev/database-wipe" in paths
    assert "/api/v1/lineup/items/{item_id}" in paths
    assert "/api/v1/lineup/items/bulk" in paths
    assert "/api/v1/lineup/items/{item_id}/events" in paths
    assert "/api/v1/imports/templates" in paths
    assert "/api/v1/imports/templates/{slug}/sample" in paths
    assert "/api/v1/imports/product-master/jobs" in paths
    assert "/api/v1/imports/product-master/jobs/{job_id}/state" in paths
    assert "/api/v1/imports/product-master/jobs/{job_id}/mapping" in paths
    assert "/api/v1/imports/product-master/jobs/{job_id}/validate" in paths
    assert "/api/v1/imports/product-master/jobs/{job_id}/commit" in paths
