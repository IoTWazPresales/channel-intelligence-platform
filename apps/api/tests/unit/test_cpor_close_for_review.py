"""Close for review (Warren 2026-11-27): sales dated inside the window, forecast as the target,
existing `ended` status, close only once the customer's sales cover the window end.

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
    FLAG_SALES_NOT_THROUGH_WINDOW_END,
    HELD_EVENT_TYPE,
    SaleRow,
    close_case_for_review,
    close_due_cases,
    due_for_review,
    reconcile_window,
    sales_covered_through,
)
from app.services.cpor.promotion_type_vocab import (
    CUSTOMER_SELL_THROUGH,
    DISTRIBUTOR_SELL_OUT,
    PROMOTION_FAMILIES,
)

TODAY = date(2026, 11, 27)
WINDOW_END = date(2026, 11, 22)
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
        window_end=WINDOW_END,
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


# --- sale-date rule -------------------------------------------------------------------------


def test_counts_only_sales_dated_inside_the_window_with_no_lookback():
    case = _case()
    sales = [
        SaleRow(1, date(2026, 10, 26), 500, False),  # before the window: no 31-day lookback
        SaleRow(1, date(2026, 11, 2), 10, False),  # first day: counted
        SaleRow(1, date(2026, 11, 16), 15, False),
        SaleRow(1, date(2026, 11, 22), 5, False),  # last day: counted
        SaleRow(1, date(2026, 11, 23), 99, False),  # after the window: not counted
        SaleRow(2, date(2026, 11, 9), 40, False),  # product not on the case: ignored
    ]
    rec = reconcile_window(case, [_line(1, 1, 60)], sales, covered_through=WINDOW_END)
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
    rec = reconcile_window(case, lines, sales, covered_through=WINDOW_END)
    by_pid = {g["product_id"]: g for g in rec["lines"]}
    assert by_pid[1]["line_ids"] == [1, 2]
    assert by_pid[1]["target_units"] == 30
    assert by_pid[1]["actual_units"] == 12
    assert by_pid[2]["window_start"] == "2026-11-09"
    assert by_pid[2]["actual_units"] == 8
    assert rec["actual_units"] == 20
    assert rec["target_units"] == 60


def test_chain_and_store_rows_are_summed_and_whole_rows_count():
    rows = [
        SaleRow(1, date(2026, 11, 16), 7, False),  # chain grain
        SaleRow(1, date(2026, 11, 16), 3, False),  # store grain, same week
        SaleRow(1, date(2026, 11, 1), 400, False),  # a month row starting before the window
    ]
    rec = reconcile_window(_case(), [_line(1, 1, 10)], rows, covered_through=WINDOW_END)
    assert rec["actual_units"] == 10


def test_voided_lines_are_not_part_of_the_target():
    rec = reconcile_window(
        _case(),
        [_line(1, 1, 40), _line(2, 1, 25, remark="[voided] wrong sku")],
        [],
        covered_through=WINDOW_END,
    )
    assert rec["target_units"] == 40


def test_flags_missing_or_short_sales_and_month_to_date_rows_count():
    case = _case()
    none_loaded = reconcile_window(case, [_line(1, 1, 10)], [], covered_through=None)
    assert FLAG_NO_SALES_LOADED in none_loaded["flags"]
    assert none_loaded["actual_units"] == 0

    short = reconcile_window(
        case,
        [_line(1, 1, 10)],
        [SaleRow(1, date(2026, 11, 9), 4, True)],
        covered_through=date(2026, 11, 15),
    )
    assert FLAG_SALES_NOT_THROUGH_WINDOW_END in short["flags"]
    assert FLAG_MTD_ESTIMATE in short["flags"]
    assert FLAG_MTD_ESTIMATE in short["lines"][0]["flags"]
    assert short["actual_units"] == 4


# --- coverage -------------------------------------------------------------------------------


def test_coverage_is_the_latest_period_end_over_all_period_types():
    assert sales_covered_through({}) is None
    assert sales_covered_through({"weekly": date(2026, 11, 16)}) == date(2026, 11, 22)
    assert sales_covered_through({"daily": date(2026, 11, 21)}) == date(2026, 11, 21)
    assert sales_covered_through(
        {"weekly": date(2026, 11, 9), "monthly": date(2026, 11, 1)}
    ) == date(2026, 11, 30)


# --- due ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "approved"},  # never activated: never ran, never auto-closes
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


# --- close and hold -------------------------------------------------------------------------


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

    def scalar(self, _stmt):
        held = [e for e in self.added if getattr(e, "event_type", None) == HELD_EVENT_TYPE]
        return held[-1].payload_json if held else None

    def events(self, event_type):
        return [e for e in self.added if getattr(e, "event_type", None) == event_type]


def _rec(covered: date | None, flags=None):
    return {
        "actual_units": 30.0,
        "target_units": 60.0,
        "window_end": WINDOW_END.isoformat(),
        "sales_covered_through": covered.isoformat() if covered else None,
        "lines": [],
        "flags": flags or [],
    }


@pytest.fixture
def coverage(monkeypatch):
    state = {"covered": WINDOW_END}
    monkeypatch.setattr(cfr, "reconcile_case_window", lambda _s, _c: _rec(state["covered"]))
    return state


def test_close_moves_to_ended_records_the_reconciliation_and_leaves_result_qty(coverage):
    case = _case()
    line = _line(1, 1, 60, result_qty=None)
    session = _FakeSession()
    out = close_case_for_review(session, case, today=TODAY)

    assert out["outcome"] == "closed"
    assert case.status == "ended"
    assert case.workflow_status == "ended"
    payload = out["event"]
    assert payload["from"] == "active" and payload["to"] == "ended" and payload["action"] == "end"
    assert payload["trigger"] == "window_ended"
    assert payload["reconciliation"]["sales_covered_through"] == WINDOW_END.isoformat()
    events = session.events("transition_end")
    assert len(events) == 1
    assert events[0].actor == "system:close_for_review"
    assert line.result_qty is None


def test_close_is_idempotent(coverage):
    case = _case()
    session = _FakeSession()
    assert close_case_for_review(session, case, today=TODAY)["outcome"] == "closed"
    assert close_case_for_review(session, case, today=TODAY) is None
    assert len(session.events("transition_end")) == 1


@pytest.mark.parametrize(
    ("covered", "reason"),
    [(None, FLAG_NO_SALES_LOADED), (date(2026, 11, 15), FLAG_SALES_NOT_THROUGH_WINDOW_END)],
)
def test_sales_not_through_window_end_hold_the_case_open_and_flagged(coverage, covered, reason):
    coverage["covered"] = covered
    case = _case()
    session = _FakeSession()
    out = close_case_for_review(session, case, today=TODAY)

    assert out["outcome"] == "held"
    assert out["reason"] == reason
    assert case.status == "active"
    assert session.events("transition_end") == []
    held = session.events(HELD_EVENT_TYPE)
    assert len(held) == 1
    assert held[0].payload_json["reason"] == reason


def test_held_event_is_written_again_only_when_coverage_moves_then_the_case_closes(coverage):
    case = _case()
    session = _FakeSession()
    coverage["covered"] = date(2026, 11, 8)
    assert close_case_for_review(session, case, today=TODAY)["event_recorded"] is True
    assert close_case_for_review(session, case, today=TODAY)["event_recorded"] is False
    coverage["covered"] = date(2026, 11, 15)
    assert close_case_for_review(session, case, today=TODAY)["event_recorded"] is True
    assert len(session.events(HELD_EVENT_TYPE)) == 2
    assert case.status == "active"

    coverage["covered"] = WINDOW_END
    assert close_case_for_review(session, case, today=TODAY)["outcome"] == "closed"
    assert case.status == "ended"


def test_batch_closes_holds_and_reports_failures_without_stopping(coverage, monkeypatch):
    covered_by_case = {1: WINDOW_END, 4: date(2026, 11, 15)}
    monkeypatch.setattr(
        cfr, "reconcile_case_window", lambda _s, c: _rec(covered_by_case.get(c.id, WINDOW_END))
    )
    due = _case(id=1)
    not_due = _case(id=2, origin="stock_action")
    short = _case(id=4)
    session = _FakeSession(cases=[due, not_due, short], ids=[1, 2, 3, 4], fail_ids={3})
    out = close_due_cases(session, today=TODAY)

    assert out["candidates"] == 4
    assert out["closed"] == [1]
    assert out["held"] == [
        {
            "case_id": 4,
            "reason": FLAG_SALES_NOT_THROUGH_WINDOW_END,
            "sales_covered_through": "2026-11-15",
        }
    ]
    assert out["failed"] == [{"case_id": 3, "error": "RuntimeError"}]
    assert session.rollbacks == 1
    assert not_due.status == "active"
    assert short.status == "active"


def test_today_follows_each_tenant_reporting_date(coverage, monkeypatch):
    seen: list[str] = []

    def fake_reporting_today(tenant_id):
        seen.append(tenant_id)
        return WINDOW_END if tenant_id == "late" else TODAY

    monkeypatch.setattr(cfr, "reporting_today", fake_reporting_today)
    a = _case(id=1, tenant_id="default")
    b = _case(id=2, tenant_id="late")
    session = _FakeSession(cases=[a, b], ids=[1, 2])
    out = close_due_cases(session)

    assert seen == ["default", "late"]
    assert out["closed"] == [1]
    assert b.status == "active"  # its reporting date is still the window end


def test_manual_end_gap_stays_on_the_event_for_settlement():
    """Warren, 27 Nov: a manual end before sales cover the window is allowed.

    The reason and the actor stay on the existing event. Settlement reads that
    event. The automatic close still holds the case until sales cover the window.
    """
    reconciliation = {
        "flags": [FLAG_SALES_NOT_THROUGH_WINDOW_END],
        "sales_covered_through": "2026-11-10",
    }
    assert cfr.sales_window_gap(reconciliation) == FLAG_SALES_NOT_THROUGH_WINDOW_END
    assert cfr.sales_window_gap({"flags": []}) is None

    record = cfr.gap_record_from_event(
        "planner:ada",
        {
            "sales_window_gap": FLAG_SALES_NOT_THROUGH_WINDOW_END,
            "reason": "Customer pulled the week",
            "actor": "planner:ada",
            "reconciliation": reconciliation,
        },
    )
    assert record == {
        "flag": FLAG_SALES_NOT_THROUGH_WINDOW_END,
        "label": "sales do not cover the window end",
        "reason": "Customer pulled the week",
        "actor": "planner:ada",
    }
    assert cfr.gap_record_from_event("system:close_for_review", {"reconciliation": {"flags": []}}) is None


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
