"""Unit tests for CST report-slot advance + article-alias steward helpers.

Uses in-memory SQLite-style mocks via MagicMock session patterns where possible;
frozen-clock tests exercise advance_cst_report_slots pure logic with a fake session.
ALLOW_TESTS_ON_DEV_DB must stay unset — these tests do not touch cip.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.imports.cst_d1 import (
    advance_cst_report_slots,
    confirm_customer_article_alias,
    reject_customer_article_alias,
)


def _monday(d: date) -> date:
    return d.fromordinal(d.toordinal() - d.weekday())


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value] if self._value is not None else []


def test_advance_creates_due_on_monday_for_key_account():
    """Monday after prior week → status due."""
    monday = date(2026, 7, 6)  # ISO Monday
    prior_week = date(2026, 6, 29)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=True)
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    session.scalar.return_value = None  # no existing slot
    added = []
    session.add.side_effect = lambda obj: added.append(obj)

    result = advance_cst_report_slots(session, as_of=monday, now=datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc))
    assert result["created"] == 1
    assert result["week_start"] == prior_week.isoformat()
    assert len(added) == 1
    assert added[0].status == "due"
    assert added[0].week_start_date == prior_week


def test_advance_creates_late_on_tuesday():
    tuesday = date(2026, 7, 7)
    prior_week = date(2026, 6, 29)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=True)
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    session.scalar.return_value = None
    added = []
    session.add.side_effect = lambda obj: added.append(obj)

    result = advance_cst_report_slots(session, as_of=tuesday)
    assert result["created"] == 1
    assert added[0].status == "late"
    assert added[0].week_start_date == prior_week


def test_advance_creates_missing_after_tuesday():
    wednesday = date(2026, 7, 8)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=True)
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    session.scalar.return_value = None
    added = []
    session.add.side_effect = lambda obj: added.append(obj)

    result = advance_cst_report_slots(session, as_of=wednesday)
    assert result["created"] == 1
    assert added[0].status == "missing"


def test_advance_due_to_late_existing_slot():
    tuesday = date(2026, 7, 7)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=True)
    slot = SimpleNamespace(status="due", late_at=None)
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    session.scalar.return_value = slot

    result = advance_cst_report_slots(
        session, as_of=tuesday, now=datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc)
    )
    assert result["created"] == 0
    assert result["advanced_late"] == 1
    assert slot.status == "late"


def test_advance_late_to_missing_after_tuesday():
    wednesday = date(2026, 7, 8)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=True)
    slot = SimpleNamespace(status="late", late_at=datetime(2026, 7, 7, tzinfo=timezone.utc))
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    session.scalar.return_value = slot

    result = advance_cst_report_slots(session, as_of=wednesday)
    assert result["advanced_missing"] == 1
    assert slot.status == "missing"


def test_advance_received_short_circuits():
    wednesday = date(2026, 7, 8)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=True)
    slot = SimpleNamespace(status="received")
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    session.scalar.return_value = slot

    result = advance_cst_report_slots(session, as_of=wednesday)
    assert result["created"] == 0
    assert result["advanced_late"] == 0
    assert result["advanced_missing"] == 0
    assert slot.status == "received"


def test_advance_skips_non_key_account():
    monday = date(2026, 7, 6)
    cfg = SimpleNamespace(customer_id=10, reports_expected=True, expected_cadence="weekly")
    cust = SimpleNamespace(id=10, is_key_account=False)
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([cfg])
    session.get.return_value = cust
    added = []
    session.add.side_effect = lambda obj: added.append(obj)

    result = advance_cst_report_slots(session, as_of=monday)
    assert result["created"] == 0
    assert added == []


def test_advance_skips_reports_expected_false():
    """reports_expected=false never appears in the config query result set."""
    monday = date(2026, 7, 6)
    session = MagicMock()
    session.scalars.return_value = _ScalarResult([])  # filtered by reports_expected.is_(True)
    result = advance_cst_report_slots(session, as_of=monday)
    assert result["created"] == 0


def test_confirm_alias_proposed_to_confirmed():
    row = SimpleNamespace(id=1, status="proposed", evidence_json={})
    session = MagicMock()
    session.get.return_value = row
    out = confirm_customer_article_alias(session, alias_id=1, actor="steward")
    assert out is row
    assert row.status == "confirmed"
    assert row.evidence_json["steward_events"][-1]["action"] == "confirm"


def test_reject_alias_writes_trail():
    row = SimpleNamespace(id=2, status="proposed", evidence_json={})
    session = MagicMock()
    session.get.return_value = row
    out = reject_customer_article_alias(session, alias_id=2, actor="steward", reason="wrong sku")
    assert out is row
    assert row.status == "rejected"
    assert row.evidence_json["steward_events"][-1]["reason"] == "wrong sku"
