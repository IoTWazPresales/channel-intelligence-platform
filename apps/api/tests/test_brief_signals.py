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


def test_fx_blocked_means_the_mode_is_missing_not_the_rate() -> None:
    """N-0083: a case with a rate and no mode is FX blocked; a case with no rate is counted apart."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from app.services import brief_signals

    cases = [
        SimpleNamespace(roe_snapshot=18.2, fx_mode=None),  # rate, no mode -> FX blocked
        SimpleNamespace(roe_snapshot=18.2, fx_mode="booked"),  # fine
        SimpleNamespace(roe_snapshot=18.2, fx_mode="floating"),  # fine
        SimpleNamespace(roe_snapshot=None, fx_mode="booked"),  # no rate -> not FX blocked
        SimpleNamespace(roe_snapshot=None, fx_mode=None),  # no rate -> not FX blocked
    ]
    first = MagicMock()
    first.scalars.return_value.all.return_value = cases
    second = MagicMock()
    second.scalar.return_value = 0

    class Db:
        def __init__(self) -> None:
            self.results = [first, second]

        async def execute(self, _stmt):
            return self.results.pop(0)

    with patch.object(brief_signals, "commercial_planner_enabled", return_value=True):
        out = asyncio.run(brief_signals._settlement_aggregates(Db(), None))
    assert out["open_cases"] == 5
    assert out["fx_blocked_cases"] == 1
    assert out["fx_rate_missing_cases"] == 2
