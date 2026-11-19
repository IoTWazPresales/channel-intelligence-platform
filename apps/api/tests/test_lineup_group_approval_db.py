"""PR #115: real group-query, ledger and audit execution on rolled-back cip_test fixtures.

The awaitable facade reuses the existing synchronous fixture connection. It does
not mock SQL, ledger or audit execution; HTTP/auth is outside these SQL tests.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.endpoints import lineup
from app.models.budget_ledger import BudgetLedgerEntry
from app.models.lineup import FactLineupPlanItem, LineupPlanItemEvent
from app.services.budget_ledger import add_entry
from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


class _AwaitableSession:
    """Delegate endpoint awaits to the fixture's real, savepoint-bound session."""

    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    async def run_sync(self, callback):
        return callback(self.session)

    async def commit(self):
        self.session.commit()

    def add(self, row):
        self.session.add(row)


@pytest.fixture
def group_rows(world: World):
    db = world.db
    identity = db.scalar(text("select current_database()"))
    print("current_database() =", identity)
    assert identity == "cip_test"
    first, other = world.customer("GROUP-A"), world.customer("GROUP-B")
    products = [world.product("GROUP-SKU-A"), world.product("GROUP-SKU-B")]
    rows = [
        FactLineupPlanItem(
            customer_id=customer.id,
            product_id=product.id,
            period_start=period,
            period_label="26Q1" if period.month == 1 else "26Q2",
            planned_volume_units=10,
            approval_status="approved",
        )
        for customer, product, period in (
            (first, products[0], date(2026, 1, 1)),
            (first, products[1], date(2026, 1, 1)),
            (other, products[0], date(2026, 1, 1)),
            (first, products[0], date(2026, 4, 1)),
        )
    ]
    db.add_all(rows)
    db.flush()
    for row in rows:
        for tag, amount in (("campaign", 12), ("non_campaign", 3)):
            add_entry(
                db,
                entry_type="reserve",
                product_line="LINE-A",
                customer_id=row.customer_id,
                product_id=row.product_id,
                landed_quarter=row.period_label,
                lineup_item_id=row.id,
                source_tag=tag,
                source_event_id=f"group-fixture:{row.id}:{tag}",
                amount_usd=amount,
            )
    ids = [row.id for row in rows]
    customer_id = first.id
    # Fixture commits release a savepoint, never its outer rollback transaction.
    db.commit()
    return customer_id, ids


def _reject(db: Session, customer_id: int):
    return asyncio.run(
        lineup.group_approve_lineup_items(
            lineup.LineupGroupApprovalBody(
                customer_id=customer_id,
                period_start=date(2026, 1, 1),
                approval_status="rejected",
                only_pending=False,
                notes=" reviewed ",
            ),
            db=_AwaitableSession(db),
            x_user_id="group-test-reviewer",
        )
    )


def _ledger(db: Session, ids: list[int]):
    return db.execute(
        select(
            BudgetLedgerEntry.lineup_item_id,
            BudgetLedgerEntry.source_tag,
            BudgetLedgerEntry.amount_usd,
        )
        .where(BudgetLedgerEntry.lineup_item_id.in_(ids))
        .order_by(BudgetLedgerEntry.id)
    ).all()


def _events(db: Session, ids: list[int]):
    return list(
        db.scalars(
            select(LineupPlanItemEvent)
            .where(LineupPlanItemEvent.lineup_item_id.in_(ids))
            .order_by(LineupPlanItemEvent.id)
        )
    )


def test_group_query_isolates_customer_and_period_and_persists_reversal_once(session, group_rows):
    customer_id, ids = group_rows
    result = _reject(session, customer_id)
    assert result["changed_ids"] == ids[:2]
    session.expire_all()
    assert [session.get(FactLineupPlanItem, iid).approval_status for iid in ids] == [
        "rejected", "rejected", "approved", "approved"
    ]
    entries = _ledger(session, ids)
    assert len(entries) == 12  # eight originals, four selected-item reversals
    assert [
        sum(float(amount) for item_id, _tag, amount in entries if item_id == iid)
        for iid in ids
    ] == [0, 0, 15, 15]
    events = _events(session, ids)
    assert [event.lineup_item_id for event in events] == ids[:2]
    assert all(
        (event.old_approval_status, event.new_approval_status, event.notes, event.actor)
        == ("approved", "rejected", "reviewed", "group-test-reviewer")
        for event in events
    )
    assert _reject(session, customer_id)["changed"] == 0
    assert _ledger(session, ids) == entries
    assert len(_events(session, ids)) == 2


def test_second_item_failure_rolls_back_status_ledger_and_audit(session, group_rows, monkeypatch):
    customer_id, ids = group_rows
    before = _ledger(session, ids)
    original = lineup.record_lineup_approval_event

    async def fail_second(db, **kwargs):
        await original(db, **kwargs)
        if kwargs["lineup_item_id"] == ids[1]:
            raise RuntimeError("second-item audit failure")

    monkeypatch.setattr(lineup, "record_lineup_approval_event", fail_second)
    with pytest.raises(RuntimeError, match="second-item audit failure"):
        with session.begin_nested():
            _reject(session, customer_id)
    session.expire_all()
    assert [session.get(FactLineupPlanItem, iid).approval_status for iid in ids] == [
        "approved", "approved", "approved", "approved"
    ]
    assert _ledger(session, ids) == before
    assert _events(session, ids) == []
