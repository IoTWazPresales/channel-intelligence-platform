"""One reporting-customer definition across modules (PR #122 round 2, B2; cip_test).

A customer merged into another, whose ``customer_report_config.reports_expected`` flag is still
true, is not a reporting customer anywhere: the line-up gate's id reader, the new-customer picker
and check, the CST upload picker, listing discovery, site onboarding, stock-not-listed, listing
coverage and the sell-through filter options. Before the merge the same customer is reporting in
each reader, so the exclusion is the merge and nothing else.

Real session inside an outer transaction rolled back at the end
(``tests/rolled_back_async_session.py``); teardown proves in a fresh session that no synthetic row
remains.
"""

from __future__ import annotations

import secrets

import pytest
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem
from sqlalchemy import func, select
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        db.info["fixture"] = {"tags": []}
        yield db
        tags = list(db.info["fixture"]["tags"])
    for tag in tags:
        fixture_customers = select(DimCustomer.id).where(DimCustomer.code.like(f"RX-{tag}-%"))
        counts = await leftover_counts(
            {
                "dim_customer": select(func.count()).where(DimCustomer.id.in_(fixture_customers)),
                "dim_product": select(func.count()).where(DimProduct.sku.like(f"RX-{tag}-%")),
                "customer_report_config": select(func.count()).where(
                    CustomerReportConfig.customer_id.in_(fixture_customers)
                ),
                "fact_lineup_plan_item": select(func.count()).where(
                    FactLineupPlanItem.customer_id.in_(fixture_customers)
                ),
            }
        )
        assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


async def _world(db, tag: str):
    db.info["fixture"]["tags"].append(tag)
    tenant = f"t-{tag}"
    keeper = DimCustomer(code=f"RX-{tag}-K", name=f"Keeper {tag}", tenant_id=tenant)
    loser = DimCustomer(code=f"RX-{tag}-L", name=f"Loser {tag}", tenant_id=tenant)
    product = DimProduct(sku=f"RX-{tag}-SKU", name=f"Product {tag}", tenant_id=tenant)
    db.add_all([keeper, loser, product])
    await db.flush()
    db.add(CustomerReportConfig(customer_id=keeper.id, reports_expected=True))
    db.add(CustomerReportConfig(customer_id=loser.id, reports_expected=True))
    await db.flush()
    return tenant, keeper, loser, product


def _sync_readers(sync_session, tenant: str) -> dict[str, set[int]]:
    """Customer ids each sync reader treats as reporting, restricted to this tenant's world."""
    from app.services.channel_intelligence.sell_through_overview import filter_options
    from app.services.imports.cst_layouts import list_reporting_customers
    from app.services.listing_capture import coverage, discovery, stock_not_listed

    options = filter_options(sync_session, tenant)
    return {
        "cst_picker": {int(c["id"]) for c in list_reporting_customers(sync_session)},
        "listing_discovery": {
            int(cust.id) for _cfg, cust in discovery._reporting_customers(sync_session, tenant)
        },
        "stock_not_listed": set(stock_not_listed._reporting_customers(sync_session, tenant, None)),
        "listing_coverage": {
            cid
            for cid, (_code, _name, reporting) in coverage._customers(sync_session, tenant).items()
            if reporting
        },
        "sell_through_filter": {
            int(c["id"]) for c in options["customers"] if c["reports_expected"]
        },
    }


def _site_onboarding_refusal(sync_session, tenant: str, customer_id: int, tag: str) -> str | None:
    from app.services.listing_capture.site_onboarding import SiteOnboardError, record_customer_site

    try:
        record_customer_site(
            sync_session,
            tenant_id=tenant,
            customer_id=customer_id,
            site_key=f"rx{tag}",
            domain=f"rx{tag}.example",
            example_urls=None,
            actor="pytest",
        )
    except SiteOnboardError as err:
        return err.code
    return None


@pytest.mark.anyio
async def test_a_merged_away_customer_with_the_flag_still_true_is_excluded_by_every_reader(session):
    from app.services.lineup.new_customer_proposal import (
        ProposalError,
        ensure_reporting_customer,
        reporting_customer_ids,
    )
    from app.services.lineup.new_customer_proposal import (
        list_reporting_customers as list_lineup_picker,
    )

    tag = secrets.token_hex(3)
    tenant, keeper, loser, _product = await _world(session, tag)

    # Before the merge: both customers are reporting in every reader.
    assert {keeper.id, loser.id} <= await reporting_customer_ids(session)
    before = await session.run_sync(lambda s: _sync_readers(s, tenant))
    for reader, ids in before.items():
        assert {keeper.id, loser.id} <= ids, reader

    # Merge the loser away; its flag stays ticked.
    loser.merged_into_customer_id = keeper.id
    await session.flush()
    flag = await session.scalar(
        select(CustomerReportConfig.reports_expected).where(
            CustomerReportConfig.customer_id == loser.id
        )
    )
    assert flag is True

    # Line-up: the gate's id reader (file writes refuse rows outside it), the new-customer picker
    # and the new-customer check. (A file row naming the loser's code is redirected to the keeper
    # by the merge redirect before the gate, so a file upload is not the probe here.)
    assert loser.id not in await reporting_customer_ids(session)
    assert keeper.id in await reporting_customer_ids(session)
    picker = await session.run_sync(lambda s: {int(c["id"]) for c in list_lineup_picker(s)})
    assert loser.id not in picker and keeper.id in picker

    def _check(sync_session) -> str:
        with pytest.raises(ProposalError) as err:
            ensure_reporting_customer(sync_session, loser.id)
        ensure_reporting_customer(sync_session, keeper.id)
        return err.value.code

    assert await session.run_sync(_check) == "customer_not_reporting"

    # CST picker, listing discovery, stock-not-listed, listing coverage, sell-through filter.
    after = await session.run_sync(lambda s: _sync_readers(s, tenant))
    for reader, ids in after.items():
        assert loser.id not in ids, reader
        assert keeper.id in ids, reader

    # Site onboarding refuses the merged-away customer before writing anything.
    code = await session.run_sync(lambda s: _site_onboarding_refusal(s, tenant, loser.id, tag))
    assert code == "not_reporting"
