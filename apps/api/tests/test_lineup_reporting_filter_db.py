"""Line-up reads show reporting customers only (Warren 2026-11-19; cip_test).

World: one reporting customer, one non-reporting customer (flag off) and one reporting customer
that is merged away into the first (flag still true), each with one draft plan item in the same
synthetic quarter. ``GET /lineup/items``, the async budget-position derivation and
``derive_planned_reservation_sync`` must see only the first customer's row. Nothing is written
beyond the fixture: real session inside an outer transaction rolled back at the end
(``tests/rolled_back_async_session.py``); teardown proves in a fresh session that no synthetic row
remains. No data migration, cleanup or delete of existing rows is involved.

Not run by the author: the coordinator runs it on cip_test.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.api.v1.endpoints import lineup as lineup_endpoint
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem
from app.services.cpor import promo_plan_builder
from app.services.lineup import budget_position
from sqlalchemy import func, select
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session

PERIOD_START = date(2098, 7, 1)
PERIOD_LABEL = "2098Q3"


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        db.info["fixture"] = {"tags": []}
        yield db
        tags = list(db.info["fixture"]["tags"])
    for tag in tags:
        fixture_customers = select(DimCustomer.id).where(DimCustomer.code.like(f"LR-{tag}-%"))
        counts = await leftover_counts(
            {
                "dim_customer": select(func.count()).where(DimCustomer.id.in_(fixture_customers)),
                "dim_product": select(func.count()).where(DimProduct.sku.like(f"LR-{tag}-%")),
                "customer_report_config": select(func.count()).where(
                    CustomerReportConfig.customer_id.in_(fixture_customers)
                ),
                "fact_lineup_plan_item": select(func.count()).where(
                    FactLineupPlanItem.customer_id.in_(fixture_customers)
                ),
            }
        )
        assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


async def _world(db):
    tag = secrets.token_hex(4)
    db.info["fixture"]["tags"].append(tag)
    tenant = f"t-{tag}"
    reporting = DimCustomer(code=f"LR-{tag}-R", name=f"Reporting {tag}", tenant_id=tenant)
    non_reporting = DimCustomer(code=f"LR-{tag}-N", name=f"Other {tag}", tenant_id=tenant)
    merged_away = DimCustomer(code=f"LR-{tag}-M", name=f"Merged {tag}", tenant_id=tenant)
    product = DimProduct(sku=f"LR-{tag}-SKU", name=f"Product {tag}", tenant_id=tenant)
    db.add_all([reporting, non_reporting, merged_away, product])
    await db.flush()
    merged_away.merged_into_customer_id = reporting.id
    db.add(CustomerReportConfig(customer_id=reporting.id, reports_expected=True))
    db.add(CustomerReportConfig(customer_id=non_reporting.id, reports_expected=False))
    # The flag is still true on the merged-away customer: the merge alone excludes it.
    db.add(CustomerReportConfig(customer_id=merged_away.id, reports_expected=True))
    for customer in (reporting, non_reporting, merged_away):
        db.add(
            FactLineupPlanItem(
                customer_id=customer.id,
                product_id=product.id,
                period_start=PERIOD_START,
                period_label=PERIOD_LABEL,
                planned_volume_units=10,
                approval_status="draft",
            )
        )
    await db.flush()
    return reporting, non_reporting, merged_away


@pytest.mark.anyio
async def test_list_items_and_pending_count_cover_only_the_reporting_customer(session):
    reporting, non_reporting, merged_away = await _world(session)
    rows = await lineup_endpoint.list_lineup_items(
        customer_id=None, channel_id=None, period_start=PERIOD_START, db=session
    )
    assert [r["customer_id"] for r in rows] == [int(reporting.id)]
    open_states = {"draft", "pending_approval", "submitted"}
    pending = [r for r in rows if r["approval_status"] in open_states]
    assert len(pending) == 1

    for hidden in (non_reporting, merged_away):
        none = await lineup_endpoint.list_lineup_items(
            customer_id=int(hidden.id), channel_id=None, period_start=PERIOD_START, db=session
        )
        assert none == []


@pytest.mark.anyio
async def test_budget_position_derivation_reads_only_the_reporting_customer(session):
    await _world(session)
    _planned, diag = await budget_position.derive_planned_reservations_with_diagnostics(
        session, period_label=PERIOD_LABEL
    )
    # No SKU assumption exists for the synthetic product, so each plan item that is read counts
    # once as skipped_missing_sku: exactly the reporting customer's one row.
    assert diag["skipped_missing_sku"] == 1


@pytest.mark.anyio
async def test_planned_reservation_sync_no_longer_reads_any_lineup(session):
    """Lane L4 (Warren 2026-11-19): the planner is sell-through only, so the sync planned
    reservation reads no line-up row, reporting customer or not. It is "not available"."""
    await _world(session)
    out = await session.run_sync(
        lambda sync: promo_plan_builder.derive_planned_reservation_sync(
            sync, period_label=PERIOD_LABEL
        )
    )
    assert out["available"] is False
    assert out["planned_reservation_usd"] is None
    assert out["skipped_missing_sku"] == 0
    assert out["planned_line_count"] == 0
