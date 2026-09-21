"""BACKLOG-160: the market placeholder payload must not report a capability as ready that has no writer."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_competitor_price_hook_is_substrate_not_ready() -> None:
    r = client.get("/api/v1/market/placeholders")
    assert r.status_code == 200
    body = r.json()
    hooks = {h["name"]: h for h in body["competitive_benchmark_hooks"]}
    hook = hooks["competitor_price_import"]
    # Flip this only when template_definitions.py gains a competitor-price template AND a writer lands.
    assert hook["status"] == "substrate"
    assert hook["status"] != "ready"
    assert hook["source"] == "imports"


def test_placeholder_payload_shape_is_preserved() -> None:
    body = client.get("/api/v1/market/placeholders").json()
    assert set(body) >= {"category_trends", "share_panel", "competitive_benchmark_hooks", "note"}
