"""Brief signals API tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.brief_signals import (
    CST_STEWARD_SLOTS_HREF,
    PROMO_NOT_ACTIVATED_HREF,
    cst_late_missing_signal,
    promo_not_activated_signal,
)

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


def test_attention_owner_and_age_are_only_ever_sourced() -> None:
    """Dashboard V2 s.4: age comes from the oldest due slot; no owner is invented."""
    from datetime import datetime, timezone

    plain = cst_late_missing_signal(late=1, missing=0)
    assert plain["owner_label"] is None and plain["age_at"] is None and plain["age_basis"] is None
    due = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
    aged = cst_late_missing_signal(late=1, missing=0, oldest_due_at=due)
    assert aged["age_at"] == "2026-11-02T08:00:00+00:00" and aged["age_basis"] == "due_at"
    assert aged["owner_label"] is None and aged["owner_user_id"] is None


def test_fx_blocked_means_the_mode_is_missing_not_the_rate() -> None:
    """N-0083: a case with a rate and no mode is FX blocked; a case with no rate is counted apart.

    The per-case rules now run inside one SQL aggregate (T1b); the rows-vs-rules check against real
    data is tests/test_t1b_brief_fx_counts_db.py. Here: the statement carries both rules, and the
    counts it returns are passed through unchanged.
    """
    import asyncio
    from unittest.mock import MagicMock, patch

    from app.services import brief_signals

    sql = str(brief_signals.open_case_fx_counts_stmt(None).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "roe_snapshot > 0" in sql  # a rate counts only above zero
    assert "fx_mode is null" in sql and "fx_mode not in ('booked', 'floating')" in sql

    first = MagicMock()
    first.one.return_value = (5, 1, 2)
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


def test_promo_not_activated_signal_links_to_activation_lens() -> None:
    none = promo_not_activated_signal(count=0)
    assert none is None
    one = promo_not_activated_signal(count=1)
    assert one is not None
    assert one["id"] == "promo_not_activated"
    assert one["action_href"] == PROMO_NOT_ACTIVATED_HREF
    assert one["title"] == "1 listing is not at promo price"
    assert one["figures"] == {"count": 1}
    many = promo_not_activated_signal(count=4)
    assert many is not None
    assert many["title"] == "4 listings are not at promo price"
    assert many["meta"] == "4 listings"
