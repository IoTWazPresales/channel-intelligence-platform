"""Step 2 (N-0122): the planner's clash card counts customer sell-through promotions only.

Warren (standing rule): "The promotion planner shows customer promotions, never sell-out."
No database: the windows and events are stubbed, the clash maths is the real one.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from app.services.cpor.customer_calendar import timeline as tl
from fastapi import HTTPException


def _promo(case_id: int, promotion_type: str | None) -> dict:
    return {
        "case_id": case_id,
        "case_code": f"C{case_id}",
        "promotion_type": promotion_type,
        "customer_id": 1,
        "window_start": date(2026, 12, 1),
        "window_end": date(2026, 12, 10),
    }


EVENTS = [{"id": 10, "customer_id": 1, "start_date": date(2026, 12, 2), "end_date": date(2026, 12, 3)}]
PROMOS = [
    _promo(1, "Sell-Through PP"),
    _promo(2, "Sell out PP"),
    _promo(3, "Stock PP (In-Direct)"),
    _promo(4, None),
]


def _run(monkeypatch, **kw):
    monkeypatch.setattr(tl, "bind_calendar_tenant", lambda *_a, **_k: None)
    monkeypatch.setattr(tl, "open_case_windows", lambda *_a, **_k: PROMOS)
    monkeypatch.setattr(tl, "calendar_events", lambda *_a, **_k: EVENTS)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [1]
    return tl.build_clash_summary(db, "t", **kw)


def test_without_a_family_every_open_promotion_counts_as_before(monkeypatch):
    assert _run(monkeypatch)["promotion_count"] == 4


def test_customer_family_counts_only_customer_sell_through(monkeypatch):
    out = _run(monkeypatch, promotion_family="customer_sell_through")
    assert (out["clash_count"], out["promotion_count"]) == (1, 1)


def test_sell_out_family_counts_only_sell_out(monkeypatch):
    out = _run(monkeypatch, promotion_family="distributor_sell_out")
    assert (out["clash_count"], out["promotion_count"]) == (1, 1)


def test_endpoint_refuses_an_unknown_family():
    from app.api.v1.endpoints import cpor_customer_calendar as ep

    with pytest.raises(HTTPException) as err:
        ep.clash_summary(_user={}, db=MagicMock(), promotion_family="everything")
    assert err.value.status_code == 400


def test_endpoint_passes_the_family_through(monkeypatch):
    from app.api.v1.endpoints import cpor_customer_calendar as ep

    seen: dict = {}

    def fake(db, tenant, **kw):
        seen.update(kw)
        return {"clash_count": 0}

    monkeypatch.setattr(ep, "build_clash_summary", fake)
    ep.clash_summary(_user={"tenant_id": "t"}, db=MagicMock(), promotion_family=" customer_sell_through ")
    assert seen["promotion_family"] == "customer_sell_through"
