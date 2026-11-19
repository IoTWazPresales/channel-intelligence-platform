"""Regressions for the BACKLOG-227 fixes merged in #96 (alignment D3, 2026-11-18).

Retired cases, the sell-through-only price, site identity and concurrent creation. The first four
tests use fakes only. The lock test opens two sessions on ``cip_test`` and writes nothing.
"""

from __future__ import annotations

import uuid

import app.services.store_dc.stock_actions as actions
import pytest
from app.services.store_dc.stock_actions import execute_aged_stock_action
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from tests.test_cpor_aged_stock_propose import _OpenResult, _writers


@pytest.fixture(autouse=True)
def _no_budget_ledger(monkeypatch):
    monkeypatch.setattr("app.services.budget_ledger.used_usd", lambda *_a, **_k: None)


def _sql(clause) -> str:
    return str(
        clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


def test_no_lineup_row_ever_sets_the_price(monkeypatch):
    """Warren 2026-11-19: price is the customer's sell-through ``unit_sell_price`` only.

    The earlier rule read line-up shelf prices and had to skip superseded rows. No line-up table
    is read now, so a superseded (or any) line-up row cannot set the price.
    """
    seen = []

    class _Rows(list):
        def all(self):
            return list(self)

    class FakeSession:
        def execute(self, statement, *_a, **_k):
            seen.append(statement)
            return _Rows([])

    assert (
        actions._srp_for_line(FakeSession(), customer_id=3, product_id=9, tenant_id="tenant-a")
        is None
    )
    assert len(seen) == 1
    sql = _sql(seen[0])
    assert "fact_customer_sellthrough" in sql
    assert "commercial_lineup" not in sql


def test_a_superseded_case_or_voided_line_is_not_an_open_action():
    seen = []

    class FakeSession:
        def execute(self, statement, *_a, **_k):
            seen.append(statement)
            return _OpenResult([])

    assert (
        actions._open_case_id(
            FakeSession(),
            tenant_id="tenant-a",
            customer_id=3,
            product_id=9,
            action="move",
            site_label="North",
        )
        is None
    )
    sql = _sql(seen[0])
    assert "superseded_by_case_id is null" in sql
    assert "[voided]" in sql
    assert "[split into layers]" in sql
    for clause in actions._retired_stock_action_clauses():
        assert _sql(clause) in sql


def _view(site_label: str):
    line = {
        "product_id": 9,
        "stock_on_hand": 12,
        "suggestions": ["promote", "move", "return"],
        "slow": True,
        "unsold": False,
    }
    return {
        "account": None,
        "sites": [{"site_label": site_label, "customer_id": 3, "lines": [line]}],
        "dc_sections": [],
    }


def _run(monkeypatch, *, view_site: str, open_rows, action: str):
    calls = []
    monkeypatch.setattr(actions, "build_customer_view", lambda *_a, **_k: _view(view_site))
    monkeypatch.setattr(actions, "_srp_for_line", lambda *_a, **_k: 100.0)
    monkeypatch.setattr(
        actions,
        "create_case_from_promo_draft",
        lambda _session, **kwargs: (
            calls.append(kwargs) or {"case_id": 6, "case_code": "CPOR-6", "href": "/x"}
        ),
    )

    class FakeSession:
        def execute(self, *_a, **_k):
            return _OpenResult(list(open_rows))

    out = execute_aged_stock_action(
        FakeSession(),
        tenant_id="tenant-a",
        customer_id=3,
        product_id=9,
        action=action,
        actor="planner",
        site_label=view_site,
        **_writers(),
    )
    return out, calls


def test_case_and_spacing_of_a_site_label_do_not_reopen_an_action(monkeypatch):
    recorded = [(5, None, {"site_labels": ["North  Store "], "stock_action": "move"})]
    out, calls = _run(monkeypatch, view_site="north store", open_rows=recorded, action="move")
    assert out["created"] is False
    assert out["reason"] == "already_open"
    assert calls == []


def test_stored_action_wins_over_an_edited_notes_marker(monkeypatch):
    # Notes were edited to say promote; the stored evidence says move.
    recorded = [(5, "stock_action=promote", {"site_labels": ["North"], "stock_action": "move"})]
    promote, calls = _run(monkeypatch, view_site="North", open_rows=recorded, action="promote")
    assert promote["created"] is True
    assert len(calls) == 1
    move, more = _run(monkeypatch, view_site="North", open_rows=recorded, action="move")
    assert move["created"] is False and move["reason"] == "already_open"
    assert more == []


def _engine():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, poolclass=NullPool)


def test_concurrent_creates_for_one_site_and_action_wait_for_each_other():
    engine = _engine()
    tenant = f"lock-test-{uuid.uuid4().hex[:10]}"
    key = dict(tenant_id=tenant, customer_id=1, product_id=2, action="move")
    try:
        with Session(engine) as first, Session(engine) as second:
            assert first.execute(text("select current_database()")).scalar_one() == "cip_test"
            actions._lock_stock_action_create(first, site_label="North", **key)

            second.execute(text("set local lock_timeout = '300ms'"))
            with pytest.raises(OperationalError):
                # Same site in another spelling: the second request must wait.
                actions._lock_stock_action_create(second, site_label="  north ", **key)
            second.rollback()

            second.execute(text("set local lock_timeout = '300ms'"))
            actions._lock_stock_action_create(
                second, site_label="South", **key
            )  # another site: no wait
            second.rollback()

            second.execute(text("set local lock_timeout = '300ms'"))
            actions._lock_stock_action_create(
                second, site_label="North", **{**key, "action": "return"}
            )
            second.rollback()

            first.rollback()  # the lock ends with the first transaction
            second.execute(text("set local lock_timeout = '300ms'"))
            actions._lock_stock_action_create(second, site_label="North", **key)
            second.rollback()
    finally:
        engine.dispose()
