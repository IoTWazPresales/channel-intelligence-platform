"""Brief signals API tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.brief_signals import CST_STEWARD_SLOTS_HREF, cst_late_missing_signal

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


def test_cst_late_missing_signal_links_to_the_steward_worklist() -> None:
    none = cst_late_missing_signal(late=0, missing=0)
    assert none is None
    both = cst_late_missing_signal(late=2, missing=1)
    assert both is not None
    assert both["id"] == "cst_reports_late_missing"
    assert both["action_href"] == CST_STEWARD_SLOTS_HREF
    assert both["figures"] == {"late": 2, "missing": 1}
    assert "3 customer sell-through reports" in both["title"]
    one = cst_late_missing_signal(late=0, missing=1)
    assert one is not None
    assert one["title"] == "1 customer sell-through report is missing"
