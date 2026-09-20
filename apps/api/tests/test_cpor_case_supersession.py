"""BACKLOG-138 — cpor_case.superseded_by_case_id writer (mocked session; no cip)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cpor.case_supersession import (
    EVENT_SUPERSEDED,
    EVENT_SUPERSEDES,
    EVENT_SUPERSESSION_RESTORED,
    preview_case_supersession,
    restore_case_supersession,
    supersede_case,
)

client = TestClient(app)


def _case(case_id: int, **over):
    base = dict(
        id=case_id,
        case_code=f"C26C{case_id:05d}",
        case_name=None,
        tenant_id="default",
        customer_id=7,
        promotion_type="Sell out PP",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
        status="approved",
        workflow_status="approved",
        superseded_by_case_id=None,
        roe_snapshot=None,
        currency_code="ZAR",
        channel="reseller",
        notes=None,
        created_by=None,
        export_version=1,
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
        created_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _session(line_count: int = 3) -> MagicMock:
    s = MagicMock()
    s.scalar = MagicMock(return_value=line_count)
    return s


def test_preview_clean_pair_has_no_blockers():
    s = _session()
    out = preview_case_supersession(s, loser=_case(1), winner=_case(2))
    assert out["blockers"] == []
    assert out["already_superseded"] is False
    assert out["loser"]["id"] == 1 and out["winner"]["id"] == 2
    assert out["loser"]["line_count"] == 3
    codes = {w["code"] for w in out["warnings"]}
    assert "loser_live" in codes  # approved loser is live → warn, not block


@pytest.mark.parametrize(
    "loser_over, winner_over, expected",
    [
        ({}, {"id": 1}, "same_case"),
        ({}, {"tenant_id": "other"}, "tenant_mismatch"),
        ({}, {"superseded_by_case_id": 9}, "winner_superseded"),
        ({}, {"status": "cancelled"}, "winner_status"),
        ({}, {"status": "rejected"}, "winner_status"),
        ({"status": "settled"}, {}, "loser_settled"),
        ({"superseded_by_case_id": 5}, {}, "loser_already_superseded"),
    ],
)
def test_preview_blockers(loser_over, winner_over, expected):
    loser = _case(1, **loser_over)
    winner = _case(2, **winner_over)
    out = preview_case_supersession(_session(), loser=loser, winner=winner)
    assert expected in {b["code"] for b in out["blockers"]}


def test_preview_warnings_customer_and_window_gap():
    loser = _case(1, window_end=date(2026, 1, 31))
    winner = _case(2, customer_id=8, promotion_type="Other", window_start=date(2026, 3, 1))
    out = preview_case_supersession(_session(), loser=loser, winner=winner)
    codes = {w["code"] for w in out["warnings"]}
    assert {"customer_mismatch", "promotion_type_mismatch", "window_gap"} <= codes
    assert out["blockers"] == []


def test_supersede_writes_pointer_keeps_status_and_records_two_events():
    s = _session()
    loser = _case(1, status="active")
    winner = _case(2, status="approved")
    out = supersede_case(s, loser=loser, winner=winner, actor="ops@local", reason="re-issued")
    assert out["written"] is True
    assert loser.superseded_by_case_id == 2
    assert loser.status == "active"  # status never touched
    assert loser.workflow_status == "approved"
    added = [c.args[0] for c in s.add.call_args_list]
    events = [a for a in added if getattr(a, "event_type", None)]
    types = {e.event_type: e for e in events}
    assert EVENT_SUPERSEDED in types and EVENT_SUPERSEDES in types
    assert types[EVENT_SUPERSEDED].case_id == 1
    assert types[EVENT_SUPERSEDED].payload_json["superseded_by_case_id"] == 2
    assert types[EVENT_SUPERSEDED].payload_json["reason"] == "re-issued"
    assert types[EVENT_SUPERSEDES].case_id == 2
    assert types[EVENT_SUPERSEDES].payload_json["supersedes_case_id"] == 1
    s.flush.assert_called()


def test_supersede_is_idempotent_for_same_winner():
    s = _session()
    loser = _case(1, superseded_by_case_id=2)
    out = supersede_case(s, loser=loser, winner=_case(2), actor="x")
    assert out["written"] is False
    assert out["already_superseded"] is True
    s.add.assert_not_called()


def test_supersede_raises_on_blockers():
    with pytest.raises(ValueError):
        supersede_case(_session(), loser=_case(1, status="settled"), winner=_case(2), actor="x")


def test_restore_clears_pointer_and_records_event():
    s = _session()
    case = _case(1, superseded_by_case_id=2)
    out = restore_case_supersession(s, case=case, actor="x", reason="oops")
    assert out["restored"] is True
    assert out["previous_superseded_by_case_id"] == 2
    assert case.superseded_by_case_id is None
    ev = [c.args[0] for c in s.add.call_args_list if getattr(c.args[0], "event_type", None)]
    assert ev and ev[0].event_type == EVENT_SUPERSESSION_RESTORED
    assert ev[0].payload_json["previous_superseded_by_case_id"] == 2


def test_restore_noop_when_not_superseded():
    s = _session()
    out = restore_case_supersession(s, case=_case(1), actor="x")
    assert out["restored"] is False
    s.add.assert_not_called()


# --- endpoints ---------------------------------------------------------------


def _patched_session(cases: dict[int, SimpleNamespace]):
    session = MagicMock()

    def _get(model, key):
        # cpor_case lookups by id; DimCustomer lookup returns a stub
        if key in cases:
            return cases[key]
        return SimpleNamespace(id=7, code="C7", name="Cust 7")

    session.get = MagicMock(side_effect=_get)
    session.scalar = MagicMock(return_value=0)
    return session


def test_endpoint_supersede_requires_confirm():
    r = client.post("/api/v1/cpor/cases/1/supersede", json={"winner_case_id": 2})
    assert r.status_code == 400


def test_endpoint_preview_and_supersede_happy_path():
    loser, winner = _case(1), _case(2)
    session = _patched_session({1: loser, 2: winner})
    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        pv = client.post("/api/v1/cpor/cases/1/supersede/preview", json={"winner_case_id": 2})
        assert pv.status_code == 200, pv.text
        assert pv.json()["blockers"] == []
        session.add.assert_not_called()  # preview is read-only

        r = client.post(
            "/api/v1/cpor/cases/1/supersede",
            json={"winner_case_id": 2, "confirm": True, "reason": "re-issue"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["superseded_by_case_id"] == 2
    assert body["status"] == "approved"
    assert body["supersession"]["written"] is True
    session.commit.assert_called_once()


def test_endpoint_supersede_409_on_blocker():
    loser, winner = _case(1, status="settled"), _case(2)
    session = _patched_session({1: loser, 2: winner})
    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        r = client.post("/api/v1/cpor/cases/1/supersede", json={"winner_case_id": 2, "confirm": True})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "supersede_blocked"
    assert loser.superseded_by_case_id is None
    session.commit.assert_not_called()


def test_endpoint_restore():
    case = _case(1, superseded_by_case_id=2)
    session = _patched_session({1: case})
    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        r = client.post("/api/v1/cpor/cases/1/supersede/restore", json={"confirm": True})
    assert r.status_code == 200, r.text
    assert r.json()["superseded_by_case_id"] is None
    assert r.json()["supersession"]["restored"] is True
