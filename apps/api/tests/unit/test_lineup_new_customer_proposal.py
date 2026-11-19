"""Final wave (a): new-customer line-up proposal, selection rules and endpoint wiring (no database).

The DB-backed rules are in tests/test_lineup_new_customer_proposal_db.py.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.deps import get_db
from app.api.v1.endpoints import lineup_new_customer as endpoint
from app.services.lineup import new_customer_proposal as svc
from app.services.lineup.new_customer_proposal import (
    FALLBACK_CUSTOMER_OWN,
    FALLBACK_MASTER,
    SOURCE_PM_BOTTOM_COST,
    SOURCE_PREVIOUS_LINEUPS,
    ProposalError,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

Q1, Q2, Q3, Q4, Q5 = (
    date(2026, 1, 1),
    date(2026, 4, 1),
    date(2026, 7, 1),
    date(2026, 10, 1),
    date(2027, 1, 1),
)


# --- period selection -------------------------------------------------------------------------


def test_recent_quarters_are_distinct_newest_first_capped_at_three_and_not_after_the_target():
    periods = [date(2026, 1, 15), date(2026, 2, 1), Q2, Q3, Q4, Q5, None]
    # Dates normalise to their calendar quarter; the target quarter is Q4 2026, so Q5 is later.
    assert svc.pick_recent_quarters(periods, up_to=date(2026, 11, 20)) == [Q4, Q3, Q2]


def test_recent_quarters_fewer_than_three_returns_what_exists():
    assert svc.pick_recent_quarters([Q1], up_to=Q4) == [Q1]
    assert svc.pick_recent_quarters([], up_to=Q4) == []


# --- customer_own vs master fallback ------------------------------------------------------------


def test_customer_with_own_rows_uses_only_own_three_most_recent_periods():
    own = [(1, Q1), (2, Q2), (3, Q3), (4, Q4)]  # four periods: oldest (product 1) drops out
    master = [(90, Q4), (91, Q3)]
    scope = svc.choose_previous_lineup_scope(own, master, up_to=Q4)
    assert scope.fallback == FALLBACK_CUSTOMER_OWN
    assert scope.periods == [Q4, Q3, Q2]
    assert sorted({pid for pid, _ in scope.rows}) == [2, 3, 4]


def test_customer_without_own_rows_falls_back_to_master_three_most_recent_periods():
    master = [(10, Q1), (11, Q2), (12, Q3), (13, Q4), (13, Q3)]
    scope = svc.choose_previous_lineup_scope([], master, up_to=Q4)
    assert scope.fallback == FALLBACK_MASTER
    assert scope.periods == [Q4, Q3, Q2]
    assert sorted({pid for pid, _ in scope.rows}) == [11, 12, 13]


def test_own_rows_only_after_the_target_period_do_not_count_as_own_history():
    scope = svc.choose_previous_lineup_scope([(1, Q5)], [(10, Q3)], up_to=Q4)
    assert scope.fallback == FALLBACK_MASTER
    assert scope.periods == [Q3]


def test_no_rows_anywhere_gives_an_empty_master_scope():
    scope = svc.choose_previous_lineup_scope([], [], up_to=Q4)
    assert scope.fallback == FALLBACK_MASTER
    assert scope.periods == []
    assert scope.rows == []


# --- proposed lines ------------------------------------------------------------------------------


def _product(
    pid: int, sku: str, name: str = "Name", marketing: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid, sku=sku, name=name, marketing_name=marketing, sales_model_name=None
    )


def test_previous_lineup_lines_are_distinct_per_product_with_the_periods_as_evidence():
    scope = svc.choose_previous_lineup_scope([], [(5, Q3), (5, Q4), (6, Q3)], up_to=Q4)
    lines = svc.previous_lineup_lines(
        scope, {5: _product(5, "S5", marketing="Five"), 6: _product(6, "S6")}
    )
    assert [ln.product_id for ln in lines] == [5, 6] or [ln.product_id for ln in lines] == [6, 5]
    by_id = {ln.product_id: ln for ln in lines}
    assert by_id[5].seed_source == SOURCE_PREVIOUS_LINEUPS
    assert by_id[5].evidence["periods"] == ["2026-10-01", "2026-07-01"]
    assert by_id[6].evidence["periods"] == ["2026-07-01"]
    assert by_id[5].label == "Five"
    assert by_id[6].label == "Name"  # falls back to the master name
    assert len({ln.product_id for ln in lines}) == len(lines)


def test_previous_lineup_lines_drop_products_that_are_not_in_the_catalogue_set():
    scope = svc.choose_previous_lineup_scope([], [(5, Q4), (404, Q4)], up_to=Q4)
    lines = svc.previous_lineup_lines(scope, {5: _product(5, "S5")})
    assert [ln.product_id for ln in lines] == [5]


def test_pm_cost_lines_carry_the_cost_and_skip_missing_costs():
    rows = [
        (_product(1, "A"), 12.5, "USD"),
        (_product(2, "B"), None, "USD"),
        (_product(3, "C"), 0, "EUR"),
    ]
    lines = svc.pm_bottom_cost_lines(rows)
    assert [ln.product_id for ln in lines] == [1, 3]
    assert lines[0].seed_source == SOURCE_PM_BOTTOM_COST
    assert lines[0].evidence == {
        "kind": "pm_bottom_cost",
        "pm_bottom_cost": 12.5,
        "currency": "USD",
    }
    assert lines[1].evidence["pm_bottom_cost"] == 0.0


# --- selection validation  ---


def test_selection_must_be_non_empty_and_inside_the_proposal():
    assert svc.validate_selection({1, 2, 3}, [3, 1, 3]) == [1, 3]
    with pytest.raises(ProposalError) as empty:
        svc.validate_selection({1}, [])
    assert empty.value.code == "no_products_selected" and empty.value.status_code == 400
    with pytest.raises(ProposalError) as outside:
        svc.validate_selection({1}, [1, 9])
    assert outside.value.code == "product_not_in_proposal" and outside.value.status_code == 400


def test_source_is_validated():
    assert svc.validate_source("pm_bottom_cost") == SOURCE_PM_BOTTOM_COST
    with pytest.raises(ProposalError) as bad:
        svc.validate_source("copy_everything")
    assert bad.value.code == "invalid_source" and bad.value.status_code == 400


# --- reporting-customer gate  ---


class _FakeSync:
    def __init__(self, reports_expected: Any):
        self._value = reports_expected

    def scalar(self, _stmt: Any) -> Any:
        return self._value


@pytest.mark.parametrize("value", [None, False])
def test_non_reporting_or_missing_config_is_refused_with_409(value):
    with pytest.raises(ProposalError) as err:
        svc.ensure_reporting_customer(_FakeSync(value), 7)
    assert err.value.status_code == 409 and err.value.code == "customer_not_reporting"


def test_reporting_customer_passes():
    svc.ensure_reporting_customer(_FakeSync(True), 7)


# --- endpoint wiring (service faked)  ---


class _FakeAsyncDb:
    def __init__(self) -> None:
        self.committed = 0
        self.rolled_back = 0
        self.added: list[Any] = []

    async def run_sync(self, fn):
        return fn(object())

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


@pytest.fixture
def client_and_db(monkeypatch):
    db = _FakeAsyncDb()
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/lineup")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    return TestClient(app), db, monkeypatch


def test_proposal_endpoint_returns_the_service_payload(client_and_db):
    client, _db, mp = client_and_db
    seen: dict[str, Any] = {}

    def fake_build(_sync, *, customer_id, source, period_start):
        seen.update(customer_id=customer_id, source=source, period_start=period_start)
        return {"source": source, "lines": [], "fallback": FALLBACK_MASTER}

    mp.setattr(endpoint, "build_proposal", fake_build)
    r = client.get(
        "/lineup/new-customer/7/proposal",
        params={"source": "previous_lineups", "period_start": "2026-10-01"},
    )
    assert r.status_code == 200
    assert r.json()["fallback"] == FALLBACK_MASTER
    assert seen == {
        "customer_id": 7,
        "source": "previous_lineups",
        "period_start": date(2026, 10, 1),
    }


def test_proposal_endpoint_maps_a_refusal_to_its_status_and_code(client_and_db):
    client, _db, mp = client_and_db

    def refuse(_sync, **_kw):
        raise ProposalError(409, "customer_not_reporting", "Customer does not report.")

    mp.setattr(endpoint, "build_proposal", refuse)
    r = client.get(
        "/lineup/new-customer/7/proposal",
        params={"source": "pm_bottom_cost", "period_start": "2026-10-01"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "customer_not_reporting"


def test_approve_records_one_audit_event_per_created_item_and_commits_once(client_and_db):
    client, db, mp = client_and_db
    events: list[dict[str, Any]] = []

    def fake_write(_sync, *, customer_id, source, period_start, product_ids, actor):
        assert (customer_id, source, actor) == (7, "pm_bottom_cost", "u1")
        return {
            "created": [{"item_id": 100 + p, "product_id": p} for p in product_ids],
            "commercial_case_id": 55,
            "period_start": period_start.isoformat(),
        }

    async def fake_event(_db, **kw):
        events.append(kw)

    mp.setattr(endpoint, "write_new_customer_lineup", fake_write)
    mp.setattr(endpoint, "record_lineup_approval_event", fake_event)
    r = client.post(
        "/lineup/new-customer/7/approve",
        json={"source": "pm_bottom_cost", "period_start": "2026-10-01", "product_ids": [3, 4]},
        headers={"X-User-Id": "u1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved_count"] == 2 and body["commercial_case_id"] == 55
    assert [e["lineup_item_id"] for e in events] == [103, 104]
    assert all(
        e["old_status"] == "draft" and e["new_status"] == "approved" and e["actor"] == "u1"
        for e in events
    )
    assert db.committed == 1 and db.rolled_back == 0


def test_approve_refusal_rolls_back_and_does_not_commit(client_and_db):
    client, db, mp = client_and_db

    def refuse(_sync, **_kw):
        raise ProposalError(409, "lineup_exists_for_period", "Already has rows.")

    mp.setattr(endpoint, "write_new_customer_lineup", refuse)
    r = client.post(
        "/lineup/new-customer/7/approve",
        json={"source": "previous_lineups", "period_start": "2026-10-01", "product_ids": [3]},
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "lineup_exists_for_period"
    assert db.committed == 0 and db.rolled_back == 1


def test_approve_rejects_an_empty_selection_at_the_schema(client_and_db):
    client, db, _mp = client_and_db
    r = client.post(
        "/lineup/new-customer/7/approve",
        json={"source": "pm_bottom_cost", "period_start": "2026-10-01", "product_ids": []},
    )
    assert r.status_code == 422 and db.committed == 0


def test_reporting_customers_endpoint_returns_the_service_list(client_and_db):
    client, _db, mp = client_and_db
    mp.setattr(
        endpoint,
        "list_reporting_customers",
        lambda _sync: [{"id": 3, "name": "Alpha"}, {"id": 4, "name": "Beta"}],
    )
    r = client.get("/lineup/new-customer/reporting-customers")
    assert r.status_code == 200
    assert r.json() == {"customers": [{"id": 3, "name": "Alpha"}, {"id": 4, "name": "Beta"}]}
