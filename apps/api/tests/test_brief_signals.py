"""Brief signals API tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_brief_signals_endpoint_shape() -> None:
    r = client.get("/api/v1/brief/signals")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "signals" in body
    assert "read" in body
    assert "spine_badges" in body
    assert "tenant_stamp" in body
    assert "tenant_name" in body
    assert "tenant_period" in body
    assert "as_of" in body
    assert isinstance(body["signals"], list)
