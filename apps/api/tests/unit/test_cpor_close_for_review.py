"""Close for review (Warren 2026-11-27): sales dated inside the window, forecast as the target,
existing `ended` status.

No database: the reconciliation is pure and the close runs against a fake session.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from app.services.cpor import close_for_review as cfr
from app.services.cpor.close_for_review import (
    FLAG_MTD_ESTIMATE,
    FLAG_NO_SALES_LOADED,
    FLAG_SALES_MAY_BE_INCOMPLETE,
    SaleRow,
    close_case_for_review,
    close_due_cases,
    due_for_review,
    reconcile_window,
)
from app.services.cpor.promotion_type_vocab import (
    CUSTOMER_SELL_THROUGH,
    DISTRIBUTOR_SELL_OUT,
    PROMOTION_FAMILIES,
)

TODAY = date(2026, 11, 27)
SELL_THROUGH_TYPE = PROMOTION_FAMILIES[CUSTOMER_SELL_THROUGH][0]
SELL_OUT_TYPE = PROMOTION_FAMILIES[DISTRIBUTOR_SELL_OUT][0]
NO_FAMILY_TYPE = "type in no family"


def _case(**kw):
    base = dict(
        id=7,
        tenant_id="default",
        customer_id=11,
        promotion_type=SELL_THROUGH_TYPE,
        status="active",
        origin="native",
        superseded_by_case_id=None,
        window_start=date(2026, 11, 2),
        window_end=date(2026, 11, 22),
        export_version=1,
        workflow_status="active",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _line(id, product_id, estimate_qty, *, remark=None, ws=None, we=None, result_qty=None):
    return SimpleNamespace(
        id=id,
        product_id=product_id,
        estimate_qty=estimate_qty,
        remark=remark,
        window_start=ws,
        window_end=we,
        result_qty=result_qty,
    )


def test_counts_only_sales_dated_inside_the_window_with_no_lookback():
    case = _case()
    sales = [
        SaleRow(
            1, date(2026, 10, 26), 500, False
        ),  # before the window: never counted (no 31-day lookback)
        SaleRow(1, date(2026, 11, 2), 10, False),  # first day: counted
        SaleRow(1, date(2026, 11, 16), 15, False),
        SaleRow(1, date(2026, 11, 22), 5, False),  # last day: counted
        SaleRow(1, date(2026, 11, 23), 99, False),  # after the window: not counted
        SaleRow(2, date(2026, 11, 9), 40, False),  # product not on the case: ignored
    ]
    rec = reconcile_window(case, [_line(1, 1, 60)], sales, sales_loaded_through=date(2026, 11, 23))
    assert rec["actual_units"] == 30
    assert rec["target_units"] == 60
    assert rec["delivery_pct"] == pytest.approx(0.5)
    assert rec["target_basis"] == "estimate_qty"
    assert rec["flags"] == []


def test_line_window_overrides_case_window_and_shared_windows_do_not_double_count():
    case = _case()
    lines = [
        _line(1, 1, 20),
        _line(2, 1, 10),  # same product and window as line 1: one group
        _line(3, 2, 30, ws=date(2026, 11, 9), we=date(2026, 11, 15)),
    ]
    sales = [
        SaleRow(1, date(2026, 11, 9), 12, False),
        SaleRow(2, date(2026, 11, 2), 50, False),  # before line 3's own window
        SaleRow(2, date(2026, 11, 9), 8, False),
    ]
    rec = reconcile_window(case, lines, sales, sales_loaded_through=date(2026, 11, 23))
    by_pid = {g["product_id"]: g for g in rec["lines"]}
    assert by_pid[1]["line_ids"] == [1, 2]
    assert by_pid[1]["target_units"] == 30
    assert by_pid[1]["actual_units"] == 12
    assert by_pid[2]["window_start"] == "2026-11-09"
    assert by_pid[2]["actual_units"] == 8
    assert rec["actual_units"] == 20
    assert rec["target_units"] == 60


def test_voided_lines_are_not_part_of_the_target():
    rec = reconcile_window(
        _case(),
        [_line(1, 1, 40), _line(2, 1, 25, remark="[voided] wrong sku")],
        [],
        sales_loaded_through=date(2026, 11, 23),
    )
    assert rec["target_units"] == 40


def test_flags_missing_or_short_sales_and_month_to_date_estimates():
    case = _case()
    none_loaded = reconcile_window(case, [_line(1, 1, 10)], [], sales_loaded_through=None)
    assert FLAG_NO_SALES_LOADED in none_loaded["flags"]
    assert none_loaded["actual_units"] == 0

    short = reconcile_window(
        case,
        [_line(1, 1, 10)],
        [SaleRow(1, date(2026, 11, 9), 4, True)],
        sales_loaded_through=date(2026, 11, 9),
    )
    assert FLAG_SALES_MAY_BE_INCOMPLETE in short["flags"]
    assert FLAG_MTD_ESTIMATE in short["flags"]
    assert FLAG_MTD_ESTIMATE in short["lines"][0]["flags"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "approved"},
        {"status": "ended"},
        {"status": "settled"},
        {"status": "cancelled"},
        {"superseded_by_case_id": 99},
        {"origin": "stock_action"},
        {"window_end": TODAY},  # window still includes today
        {"promotion_type": SELL_OUT_TYPE},
        {"promotion_type": NO_FAMILY_TYPE},
    ],
)
def test_not_due(overrides):
    assert due_for_review(_case(**overrides), TODAY) is False


def test_due_when_active_sell_through_and_window_ended_before_today():
    assert due_for_review(_case(), TODAY) is True


class _FakeSession:
    def __init__(self, cases=None, ids=None, fail_ids=()):
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0
        self._cases = {c.id: c for c in (cases or [])}
        self._ids = ids or []
        self._fail_ids = set(fail_ids)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def get(self, _model, case_id):
        if case_id in self._fail_ids:
            raise RuntimeError("boom")
        return self._cases.get(case_id)

    def scalars(self, _stmt):
        ids = self._ids
        return SimpleNamespace(all=lambda: list(ids))


@pytest.fixture
def _stub_reconcile(monkeypatch):
    rec = {"actual_units": 30.0, "target_units": 60.0, "lines": [], "flags": []}
    monkeypatch.setattr(cfr, "reconcile_case_window", lambda _s, _c: rec)
    return rec


def test_close_moves_to_ended_records_the_reconciliation_and_leaves_result_qty(_stub_reconcile):
    case = _case()
    line = _line(1, 1, 60, result_qty=None)
    session = _FakeSession()
    payload = close_case_for_review(session, case, today=TODAY)

    assert case.status == "ended"
    assert case.workflow_status == "ended"
    assert payload["from"] == "active" and payload["to"] == "ended" and payload["action"] == "end"
    assert payload["trigger"] == "window_ended"
    assert payload["reconciliation"] is _stub_reconcile
    events = [o for o in session.added if type(o).__name__ == "CporCaseEvent"]
    assert len(events) == 1
    assert events[0].event_type == "transition_end"
    assert events[0].actor == "system:close_for_review"
    assert line.result_qty is None


def test_close_is_idempotent(_stub_reconcile):
    case = _case()
    session = _FakeSession()
    assert close_case_for_review(session, case, today=TODAY) is not None
    assert close_case_for_review(session, case, today=TODAY) is None
    assert sum(1 for o in session.added if type(o).__name__ == "CporCaseEvent") == 1


def test_batch_commits_each_close_and_reports_failures_without_stopping(_stub_reconcile):
    due = _case(id=1)
    not_due = _case(id=2, origin="stock_action")
    also_due = _case(id=4)
    session = _FakeSession(cases=[due, not_due, also_due], ids=[1, 2, 3, 4], fail_ids={3})
    out = close_due_cases(session, today=TODAY)

    assert out["candidates"] == 4
    assert out["closed"] == [1, 4]
    assert out["failed"] == [{"case_id": 3, "error": "RuntimeError"}]
    assert session.commits == 2
    assert session.rollbacks == 1
    assert not_due.status == "active"


def test_daily_beat_entry_and_batch_routing():
    from app.worker.celery_app import build_beat_schedule, celery_app
    from app.worker.celery_queues import BATCH_TASK_NAMES
    from celery.schedules import crontab

    entry = build_beat_schedule()["cpor-close-ended-windows-for-review"]
    assert entry["task"] == "cpor.close_ended_windows_for_review"
    assert entry["schedule"] == crontab(hour=6, minute=45)
    assert "cpor.close_ended_windows_for_review" in BATCH_TASK_NAMES
    import app.worker.tasks  # noqa: F401 — registers the task

    assert "cpor.close_ended_windows_for_review" in celery_app.tasks
