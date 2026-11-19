"""Planner calendar-clash card (BACKLOG-254): exact tenant-wide clash count, same clash maths.

``GET /customer-calendar/clashes/summary`` reuses ``compute_clashes`` over the same open case
windows and calendar events as the per-customer timeline. No database here; DB proof is in
tests/test_customer_calendar_db.py (``test_clash_summary_*``).
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.services.cpor.customer_calendar import timeline as tl
from sqlalchemy.exc import ProgrammingError


def _promo(case_id: int, customer_id: int, start: date, end: date) -> dict:
    return {
        "case_id": case_id,
        "case_code": f"C{case_id}",
        "customer_id": customer_id,
        "window_start": start,
        "window_end": end,
    }


def _event(event_id: int, customer_id: int, start: date, end: date) -> dict:
    return {"id": event_id, "customer_id": customer_id, "start_date": start, "end_date": end}


def _run(monkeypatch, promos, events, allowed=(1, 2, 3), **kw):
    monkeypatch.setattr(tl, "bind_calendar_tenant", lambda *_a, **_k: None)
    monkeypatch.setattr(tl, "open_case_windows", lambda *_a, **_k: promos)
    monkeypatch.setattr(tl, "calendar_events", lambda *_a, **_k: events)
    db = MagicMock()
    db.scalars.return_value.all.return_value = list(allowed)
    return tl.build_clash_summary(db, "t", date_from=kw.get("date_from"), date_to=kw.get("date_to"))


def test_counts_pairs_promotions_and_customers_exactly(monkeypatch):
    promos = [
        _promo(1, 1, date(2026, 12, 1), date(2026, 12, 10)),
        _promo(2, 2, date(2026, 12, 5), date(2026, 12, 8)),
        _promo(3, 3, date(2027, 3, 1), date(2027, 3, 5)),  # no event: no clash
    ]
    events = [
        _event(10, 1, date(2026, 12, 9), date(2026, 12, 20)),
        _event(11, 1, date(2026, 12, 10), date(2026, 12, 11)),  # second event, same promotion
        _event(12, 2, date(2026, 12, 1), date(2026, 12, 4)),  # ends the day before: no clash
        _event(13, 3, date(2026, 12, 1), date(2026, 12, 31)),  # other customer's window: no clash
    ]
    out = _run(monkeypatch, promos, events)
    assert out["clash_count"] == 2
    assert out["promotion_count"] == 1
    assert out["customer_count"] == 1


def test_no_clashes_is_a_real_zero(monkeypatch):
    out = _run(monkeypatch, [], [])
    assert (out["clash_count"], out["promotion_count"], out["customer_count"]) == (0, 0, 0)


def test_customers_outside_the_account_scope_never_count(monkeypatch):
    promos = [_promo(1, 1, date(2026, 12, 1), date(2026, 12, 10))]
    events = [_event(10, 1, date(2026, 12, 2), date(2026, 12, 3))]
    out = _run(monkeypatch, promos, events, allowed=(2,))
    assert out["clash_count"] == 0


def test_the_requested_range_is_echoed(monkeypatch):
    out = _run(monkeypatch, [], [], date_from=date(2026, 11, 19))
    assert out["from"] == "2026-11-19" and out["to"] is None


def test_endpoint_reports_unavailable_not_zero_when_the_migration_is_missing(monkeypatch):
    from app.api.v1.endpoints import cpor_customer_calendar as ep

    error = ProgrammingError("select", {}, SimpleNamespace(sqlstate="42P01"))
    monkeypatch.setattr(ep, "build_clash_summary", MagicMock(side_effect=error))
    out = ep.clash_summary(date_from=None, date_to=None, _user={"tenant_id": "t"}, db=MagicMock())
    assert out["data_unavailable"] is True
    assert "clash_count" not in out


def test_endpoint_refuses_an_inverted_range():
    from app.api.v1.endpoints import cpor_customer_calendar as ep
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        ep.clash_summary(
            date_from=date(2026, 12, 2), date_to=date(2026, 12, 1), _user={}, db=MagicMock()
        )
    assert err.value.status_code == 422


def test_route_is_registered_under_the_calendar_router():
    from app.api.v1.endpoints import cpor_customer_calendar as ep

    assert "/clashes/summary" in [getattr(r, "path", "") for r in ep.router.routes]
