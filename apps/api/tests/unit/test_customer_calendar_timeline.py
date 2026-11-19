"""Timeline reuses the owning line-void rule and tolerates an unapplied migration."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.customer_calendar.timeline import _voided_case_ids
from sqlalchemy.exc import ProgrammingError


def test_only_cases_with_every_line_voided_are_hidden():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(case_id=1, remark="[voided]", estimate_qty=0),
        SimpleNamespace(case_id=2, remark="[split into layers]", estimate_qty=5),
        SimpleNamespace(case_id=2, remark="Live", estimate_qty=5),
        SimpleNamespace(case_id=3, remark="[split into layers]", estimate_qty=0),
    ]
    assert _voided_case_ids(db, [1, 2, 3, 4]) == {1, 3}


def test_timeline_reports_unavailable_when_calendar_migration_is_missing(monkeypatch):
    from app.api.v1.endpoints import cpor_customer_calendar as endpoint

    error = ProgrammingError("select", {}, SimpleNamespace(sqlstate="42P01"))
    monkeypatch.setattr(endpoint, "build_timeline", MagicMock(side_effect=error))
    db = MagicMock()
    out = endpoint.customer_timeline(
        customer_id=17,
        date_from=None,
        date_to=None,
        _user={"tenant_id": "tenant-a"},
        db=db,
    )
    assert out["data_unavailable"] is True
    assert out["promotions"] == out["calendar_events"] == out["clashes"] == []
