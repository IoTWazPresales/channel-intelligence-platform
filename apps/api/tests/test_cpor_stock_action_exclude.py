"""Move and Return cases stay out of commercial intelligence (BACKLOG-227, 2026-11-18).

The endpoint function is called directly with a faked case and session, so nothing
is read from or written to a database.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import app.api.v1.endpoints.cpor_cases as cases_ep
import pytest
from app.services.cpor.intelligence_scope import STOCK_ACTION_ORIGIN
from fastapi import HTTPException


@pytest.fixture()
def fake_case(monkeypatch):
    holder: dict = {}
    events: list[dict] = []

    class _S:
        def add(self, _obj):
            return None

        def commit(self):
            holder["committed"] = True

    @contextmanager
    def _local():
        yield _S()

    monkeypatch.setattr(cases_ep, "SessionLocal", _local)
    monkeypatch.setattr(cases_ep, "_load_case", lambda _s, _cid, _u=None: holder["case"])
    monkeypatch.setattr(cases_ep, "_record_event", lambda *_a, **k: events.append(k))
    return holder, events


def _set(case_id, exclude):
    return cases_ep.set_intelligence_exclude(
        case_id,
        cases_ep.IntelligenceExcludeBody(exclude=exclude, confirm=True),
        user={"id": 1, "email": "planner@example.com"},
    )


def test_a_move_or_return_case_cannot_rejoin_intelligence(fake_case):
    holder, events = fake_case
    holder["case"] = SimpleNamespace(
        id=7, case_code="C-7", origin=STOCK_ACTION_ORIGIN, intelligence_exclude=True
    )
    with pytest.raises(HTTPException) as err:
        _set(7, False)
    assert err.value.status_code == 409
    assert "stock_action_case_stays_excluded" in err.value.detail
    assert holder["case"].intelligence_exclude is True
    assert events == [] and "committed" not in holder

    assert _set(7, True)["intelligence_exclude"] is True


def test_other_cases_can_still_clear_the_flag(fake_case):
    holder, events = fake_case
    holder["case"] = SimpleNamespace(
        id=8, case_code="C-8", origin="proposed_by_cip", intelligence_exclude=True
    )
    assert _set(8, False)["intelligence_exclude"] is False
    assert events and events[0]["payload"] == {"exclude": False}
