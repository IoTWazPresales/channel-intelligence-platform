"""Final wave (a): new-customer line-up proposal and approval against the database (cip_test only).

Write-capable DB test: every row is created inside one session and rolled back at the end (the
approve endpoint's commit is turned into a flush by ``_NoCommit``). Rows use a private tenant tag so
nothing already in the database can leak into the master-line-up fallback assertions.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.api.v1.endpoints.lineup_new_customer import (
    NewCustomerApproveBody,
    approve_new_customer_lineup,
    get_new_customer_proposal,
)
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem, LineupPlanItemEvent
from fastapi import HTTPException
from sqlalchemy import func, select

Q1, Q2, Q3, Q4 = date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)
TARGET = date(2026, 10, 1)


class _NoCommit:
    """Wraps the real session; commit becomes flush and rollback is deferred to the test."""

    def __init__(self, db):
        self._db = db
        self.rollbacks = 0

    def __getattr__(self, name):
        return getattr(self._db, name)

    async def commit(self):
        await self._db.flush()

    async def rollback(self):
        self.rollbacks += 1


async def _customer(db, tag: str, suffix: str, *, reports: bool | None) -> DimCustomer:
    c = DimCustomer(code=f"NC-{tag}-{suffix}", name=f"NC {tag} {suffix}", tenant_id=f"t-{tag}")
    db.add(c)
    await db.flush()
    if reports is not None:
        db.add(CustomerReportConfig(customer_id=c.id, reports_expected=reports))
        await db.flush()
    return c


async def _product(
    db, tag: str, suffix: str, *, cost: float | None = None, active: bool = True
) -> DimProduct:
    p = DimProduct(
        sku=f"NC-{tag}-{suffix}", name=f"Product {suffix}", tenant_id=f"t-{tag}", is_active=active
    )
    db.add(p)
    await db.flush()
    if cost is not None:
        db.add(CommercialSkuAssumption(product_id=p.id, controlled_cost_amount=cost))
        await db.flush()
    return p


async def _case_with_lines(
    db,
    period: date,
    lines: list[tuple[int, int | None]],
    *,
    status: str = "accepted",
    superseded_by: int | None = None,
) -> CommercialLineupCase:
    case = CommercialLineupCase(
        period_label=str(period),
        inferred_period_start=period,
        commercial_status=status,
        superseded_by_case_id=superseded_by,
    )
    db.add(case)
    await db.flush()
    for product_id, customer_id in lines:
        db.add(
            CommercialLineupLine(
                case_id=case.id,
                product_id=product_id,
                customer_id=customer_id,
                row_status="imported",
            )
        )
    await db.flush()
    return case


async def _proposal(db, customer_id: int, source: str, period: date = TARGET) -> dict:
    return await get_new_customer_proposal(customer_id, source=source, period_start=period, db=db)


async def _refusal(db, customer_id: int, source: str, period: date = TARGET) -> dict:
    with pytest.raises(HTTPException) as err:
        await _proposal(db, customer_id, source, period)
    return {"status": err.value.status_code, **err.value.detail}


@pytest.fixture
async def session():
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


@pytest.mark.anyio
async def test_pm_bottom_cost_source_lists_active_items_with_a_cost_and_shows_the_cost(session):
    tag = secrets.token_hex(3)
    cust = await _customer(session, tag, "a", reports=True)
    with_cost = await _product(session, tag, "cost", cost=12.5)
    await _product(session, tag, "nocost")
    await _product(session, tag, "inactive", cost=3, active=False)

    out = await _proposal(session, cust.id, "pm_bottom_cost")
    assert out["source"] == "pm_bottom_cost" and out["fallback"] is None
    assert [ln["product_id"] for ln in out["lines"]] == [with_cost.id]
    assert out["lines"][0]["evidence"]["pm_bottom_cost"] == 12.5
    assert out["line_count"] == 1


@pytest.mark.anyio
async def test_non_reporting_customer_is_refused_with_409(session):
    tag = secrets.token_hex(3)
    flagged_false = await _customer(session, tag, "f", reports=False)
    no_config = await _customer(session, tag, "n", reports=None)
    for cust in (flagged_false, no_config):
        for source in ("pm_bottom_cost", "previous_lineups"):
            assert (await _refusal(session, cust.id, source))["status"] == 409
            assert (await _refusal(session, cust.id, source))["code"] == "customer_not_reporting"
    assert (await _refusal(session, 2_000_000_000, "pm_bottom_cost"))["status"] == 404


@pytest.mark.anyio
async def test_customer_with_existing_rows_for_the_period_is_refused_with_409(session):
    tag = secrets.token_hex(3)
    via_fact = await _customer(session, tag, "fact", reports=True)
    via_master = await _customer(session, tag, "master", reports=True)
    prod = await _product(session, tag, "p", cost=1)
    session.add(
        FactLineupPlanItem(
            customer_id=via_fact.id, period_start=TARGET, product_id=prod.id, planned_volume_units=0
        )
    )
    await _case_with_lines(session, TARGET, [(prod.id, via_master.id)])
    await session.flush()
    for cust in (via_fact, via_master):
        refusal = await _refusal(session, cust.id, "pm_bottom_cost")
        assert (refusal["status"], refusal["code"]) == (409, "lineup_exists_for_period")


@pytest.mark.anyio
async def test_previous_lineups_falls_back_to_master_three_most_recent_periods_excluding_superseded(
    session,
):
    tag = secrets.token_hex(3)
    new = await _customer(session, tag, "new", reports=True)
    other = await _customer(session, tag, "other", reports=True)
    old, mid, recent, newest, gone, cancelled = [await _product(session, tag, s) for s in "abcdef"]
    await _case_with_lines(session, Q1, [(old.id, other.id)])  # fourth most recent: dropped
    await _case_with_lines(session, Q2, [(mid.id, other.id)])
    await _case_with_lines(session, Q3, [(recent.id, other.id)])
    await _case_with_lines(
        session, Q4, [(newest.id, other.id)]
    )  # other customer, same quarter as the target
    newer = await _case_with_lines(session, Q4, [(newest.id, other.id)])
    await _case_with_lines(
        session, Q4, [(gone.id, other.id)], status="superseded", superseded_by=newer.id
    )
    await _case_with_lines(session, Q4, [(cancelled.id, other.id)], status="cancelled")

    out = await _proposal(session, new.id, "previous_lineups")
    assert out["fallback"] == "master"
    assert out["periods_used"] == ["2026-10-01", "2026-07-01", "2026-04-01"]
    assert {ln["product_id"] for ln in out["lines"]} == {mid.id, recent.id, newest.id}
    by_id = {ln["product_id"]: ln for ln in out["lines"]}
    assert by_id[newest.id]["evidence"]["periods"] == ["2026-10-01"]
    assert by_id[newest.id]["evidence"]["scope"] == "master"
    assert "master" in out["basis"].lower()


@pytest.mark.anyio
async def test_previous_lineups_uses_the_customers_own_periods_when_it_has_rows(session):
    tag = secrets.token_hex(3)
    cust = await _customer(session, tag, "own", reports=True)
    other = await _customer(session, tag, "other", reports=True)
    own_a, own_b, master_only = [await _product(session, tag, s) for s in "xyz"]
    await _case_with_lines(session, Q2, [(own_a.id, cust.id)])
    await _case_with_lines(session, Q3, [(own_b.id, cust.id)])
    await _case_with_lines(session, Q3, [(master_only.id, other.id)])

    out = await _proposal(session, cust.id, "previous_lineups")
    assert out["fallback"] == "customer_own"
    assert out["periods_used"] == ["2026-07-01", "2026-04-01"]
    assert {ln["product_id"] for ln in out["lines"]} == {own_a.id, own_b.id}
    assert "own" in out["basis"].lower()


@pytest.mark.anyio
async def test_approve_creates_the_ticked_lines_approved_with_audit_in_one_transaction(session):
    tag = secrets.token_hex(3)
    cust = await _customer(session, tag, "new", reports=True)
    keep = await _product(session, tag, "keep", cost=5)
    untick = await _product(session, tag, "untick", cost=6)
    db = _NoCommit(session)

    body = NewCustomerApproveBody(
        source="pm_bottom_cost", period_start=TARGET, product_ids=[keep.id]
    )
    out = await approve_new_customer_lineup(cust.id, body, db=db, x_user_id="tester")
    assert out["approved_count"] == 1 and out["fallback"] is None

    items = (
        (
            await session.execute(
                select(FactLineupPlanItem).where(FactLineupPlanItem.customer_id == cust.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(i.product_id, i.approval_status, float(i.planned_volume_units)) for i in items] == [
        (keep.id, "approved", 0.0)
    ]
    events = (
        (
            await session.execute(
                select(LineupPlanItemEvent).where(LineupPlanItemEvent.lineup_item_id == items[0].id)
            )
        )
        .scalars()
        .all()
    )
    assert [(e.old_approval_status, e.new_approval_status, e.actor) for e in events] == [
        ("draft", "approved", "tester")
    ]

    case = await session.get(CommercialLineupCase, out["commercial_case_id"])
    assert (
        case.commercial_status == "accepted"
        and case.accepted_by == "tester"
        and case.inferred_period_start == TARGET
    )
    lines = (
        (
            await session.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.case_id == case.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(ln.product_id, ln.customer_id, ln.quantity_units) for ln in lines] == [
        (keep.id, cust.id, None)
    ]
    assert untick.id not in {ln.product_id for ln in lines}

    # A second approval for the same period is refused and writes nothing more.
    with pytest.raises(HTTPException) as again:
        await approve_new_customer_lineup(cust.id, body, db=db, x_user_id="tester")
    assert (
        again.value.status_code == 409 and again.value.detail["code"] == "lineup_exists_for_period"
    )
    count = await session.scalar(
        select(func.count())
        .select_from(FactLineupPlanItem)
        .where(FactLineupPlanItem.customer_id == cust.id)
    )
    assert count == 1


@pytest.mark.anyio
async def test_approve_refuses_products_outside_the_proposal_and_non_reporting_customers(session):
    tag = secrets.token_hex(3)
    cust = await _customer(session, tag, "new", reports=True)
    off = await _customer(session, tag, "off", reports=False)
    listed = await _product(session, tag, "listed", cost=5)
    unlisted = await _product(session, tag, "unlisted")
    db = _NoCommit(session)

    with pytest.raises(HTTPException) as outside:
        await approve_new_customer_lineup(
            cust.id,
            NewCustomerApproveBody(
                source="pm_bottom_cost", period_start=TARGET, product_ids=[listed.id, unlisted.id]
            ),
            db=db,
            x_user_id=None,
        )
    assert (
        outside.value.status_code == 400
        and outside.value.detail["code"] == "product_not_in_proposal"
    )
    with pytest.raises(HTTPException) as not_reporting:
        await approve_new_customer_lineup(
            off.id,
            NewCustomerApproveBody(
                source="pm_bottom_cost", period_start=TARGET, product_ids=[listed.id]
            ),
            db=db,
            x_user_id=None,
        )
    assert (
        not_reporting.value.status_code == 409
        and not_reporting.value.detail["code"] == "customer_not_reporting"
    )
    written = await session.scalar(
        select(func.count())
        .select_from(FactLineupPlanItem)
        .where(FactLineupPlanItem.customer_id.in_([cust.id, off.id]))
    )
    assert written == 0


@pytest.mark.anyio
async def test_reporting_customer_list_has_only_reporting_unmerged_customers(session):
    from app.api.v1.endpoints.lineup_new_customer import get_new_customer_reporting_customers

    tag = secrets.token_hex(3)
    reporting = await _customer(session, tag, "yes", reports=True)
    not_reporting = await _customer(session, tag, "no", reports=False)
    no_config = await _customer(session, tag, "none", reports=None)
    merged = await _customer(session, tag, "merged", reports=True)
    merged.merged_into_customer_id = reporting.id
    await session.flush()

    ids = {c["id"] for c in (await get_new_customer_reporting_customers(db=session))["customers"]}
    assert reporting.id in ids
    assert not ({not_reporting.id, no_config.id, merged.id} & ids)
