"""L4 sell-through-only planner SQL proofs. Coordinator runs on cip_test, never live cip.

All fixture rows live inside rolled_back_async_session, including any service commits.
No mocks replace the source reads. Decoys exercise every source removed from the planner.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.cpor import CporCase, CporCaseLine
from app.models.derived import WeeksOfCoverObservation
from app.models.dimensions import (
    DimCompetitorBrand,
    DimCompetitorProduct,
    DimCustomer,
    DimDistributor,
    DimProduct,
)
from app.models.fact_customer_sellthrough import FactCustomerSellthrough as ST
from app.models.fact_demand_forecast import FactDemandForecast
from app.models.facts import (
    FactBuyPlan,
    FactCompetitorMapping,
    FactCompetitorPrice,
    FactInboundShipment,
    FactSalesSellout,
)
from app.models.lineup import FactLineupPlanItem
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.cpor import planner_sellthrough as st
from app.services.cpor import promo_plan_builder as builder
from app.services.cpor.intake_weighted_mac import suggest_sellthrough_mac
from app.services.store_dc.stock_actions import _srp_for_line
from sqlalchemy import func, select, update
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session

PERIOD = "2098Q2"
START = date(2098, 4, 7)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def world(monkeypatch):
    monkeypatch.setenv(st.RUN_RATE_WEEKS_ENV, "8")
    tag = f"L4-{secrets.token_hex(5)}"
    async with rolled_back_async_session() as db:
        customer = DimCustomer(code=f"{tag}-C", name=tag, tenant_id=tag)
        other = DimCustomer(code=f"{tag}-O", name=tag, tenant_id=tag)
        product = DimProduct(sku=f"{tag}-P", name=tag, tenant_id=tag)
        decoy = DimProduct(sku=f"{tag}-D", name=tag, tenant_id=tag)
        distributor = DimDistributor(code=f"{tag}-D", name=tag, tenant_id=tag)
        brand = DimCompetitorBrand(name=tag)
        db.add_all([customer, other, product, decoy, distributor, brand])
        await db.flush()
        rival = DimCompetitorProduct(brand_id=brand.id, sku=tag, name=tag)
        lineup = CommercialLineupCase(period_label=PERIOD, commercial_status="accepted")
        earlier = CporCase(
            case_code=tag,
            tenant_id=tag,
            customer_id=customer.id,
            promotion_type="Sell out PP",
            window_start=START,
            window_end=START + timedelta(weeks=13),
            status="settled",
        )
        listing = CustomerListing(
            customer_id=customer.id,
            product_id=product.id,
            url=f"https://example.invalid/{tag}",
            marketplace="fixture",
        )
        db.add_all([rival, lineup, earlier, listing])
        await db.flush()
        # Nine weekly reports: the first is outside the configured eight-report window.
        for i, units in enumerate([9999, 10, 20, 30, 40, 50, 60, 70, 80]):
            db.add(
                ST(
                    source_key=f"{tag}-ST-{i}",
                    tenant_id=tag,
                    customer_id=customer.id,
                    product_id=product.id,
                    period_start_date=START + timedelta(weeks=i),
                    period_type="weekly",
                    period_grain="week",
                    units_sold=units,
                    unit_sell_price=250 if i == 7 else (200 if i < 7 else None),
                    unit_mac=100 if i == 8 else 90,
                    unit_cost=120,
                    reported_soh=180,
                    vat_basis="ex_vat",
                )
            )
        # Newer non-weekly prices/costs must not beat the latest reported WEEK.
        db.add(
            ST(
                source_key=f"{tag}-MONTH",
                tenant_id=tag,
                customer_id=customer.id,
                product_id=product.id,
                period_start_date=START + timedelta(weeks=10),
                period_type="month",
                period_grain="month",
                units_sold=9999,
                unit_sell_price=9999,
                unit_mac=9999,
            )
        )
        # Same product, different customer; and wrong tenant with the same customer FK.
        for label, cid, tenant in [
            ("OTHER", other.id, tag),
            ("TENANT", customer.id, f"{tag}-foreign"),
        ]:
            db.add(
                ST(
                    source_key=f"{tag}-{label}",
                    tenant_id=tenant,
                    customer_id=cid,
                    product_id=product.id,
                    period_start_date=START + timedelta(weeks=12),
                    period_type="week",
                    units_sold=9999,
                    unit_sell_price=9999,
                    unit_mac=9999,
                    reported_soh=9999,
                )
            )
        for candidate in (product, decoy):
            db.add(
                CommercialLineupLine(
                    case_id=lineup.id,
                    customer_id=customer.id,
                    product_id=candidate.id,
                    distributor_id=distributor.id,
                    msrp_local=9999,
                    dap_evidence_local=9999,
                    quantity_units=9999,
                )
            )
            db.add(
                FactLineupPlanItem(
                    customer_id=customer.id,
                    product_id=candidate.id,
                    period_start=date(2098, 4, 1),
                    period_label=PERIOD,
                    planned_volume_units=9999,
                )
            )
            db.add(CommercialSkuAssumption(product_id=candidate.id, controlled_cost_amount=9999))
            db.add(
                CporCaseLine(
                    case_id=earlier.id,
                    product_id=candidate.id,
                    distributor_id=distributor.id,
                    window_start=earlier.window_start,
                    window_end=earlier.window_end,
                    pod_quarter=PERIOD,
                    srp=9999,
                    vat_rate=0.15,
                    dealer_margin_pct=0.1,
                    estimate_qty=9999,
                    cost_basis=9999,
                    cost_source="manual",
                )
            )
        db.add_all(
            [
                FactDemandForecast(
                    tenant_id=tag,
                    distributor_id=distributor.id,
                    product_id=product.id,
                    customer_id=customer.id,
                    period_start=START,
                    forecast_units=9999,
                    method="manual",
                    confidence_level="override",
                    source_key=f"{tag}-FORECAST",
                ),
                ListingObservation(
                    listing_id=listing.id,
                    fetched_at=datetime.now(UTC),
                    parser_version="fixture",
                    extracted_price=9999,
                ),
                FactCompetitorMapping(
                    product_id=product.id,
                    competitor_product_id=rival.id,
                    score=1,
                    explanation="fixture",
                    approval_status="approved",
                ),
                FactCompetitorPrice(
                    competitor_product_id=rival.id,
                    observed_at=datetime.now(UTC),
                    price=9999,
                ),
                FactInboundShipment(
                    source_key=f"{tag}-SHIP",
                    fact_upsert_key=f"{tag}-SHIP",
                    tenant_id=tag,
                    product_id=product.id,
                    customer_id=customer.id,
                    distributor_id=distributor.id,
                    report_type="shipment",
                    line_state="delivered",
                    quantity=9999,
                    unit_price=9999,
                    pod_date=START,
                    product_resolution_status="resolved",
                    distributor_resolution_status="resolved",
                ),
                FactBuyPlan(
                    product_id=product.id,
                    distributor_id=distributor.id,
                    recommended_qty=9999,
                    recommended_window_start=START,
                    recommended_window_end=START + timedelta(weeks=13),
                    rationale="fixture",
                ),
                FactSalesSellout(
                    source_key=f"{tag}-DSI",
                    tenant_id=tag,
                    product_id=product.id,
                    customer_id=customer.id,
                    distributor_id=distributor.id,
                    period_start=START,
                    transaction_date=START,
                    units=9999,
                    revenue=9999,
                    unit_sellout_price_ex_tax_amount=9999,
                ),
                WeeksOfCoverObservation(
                    source_key=f"{tag}-WOC",
                    tenant_id=tag,
                    distributor_id=distributor.id,
                    product_id=product.id,
                    snapshot_date=START,
                    cover_as_of_date=START,
                    observed_at=datetime.now(UTC),
                    trigger="as_of_backfill",
                    reported_soh=9999,
                    sell_out_since=0,
                    landed_since=0,
                    derived_stock=9999,
                    weekly_velocity=1,
                    weeks_of_cover=9999,
                    replenishment_threshold_weeks=6,
                ),
            ]
        )
        await db.flush()
        lineup_id, listing_id = lineup.id, listing.id
        yield db, tag, customer.id, product.id, decoy.id, earlier.id
    # Prove rollback across all fixture tables from a fresh session.
    customers = select(DimCustomer.id).where(DimCustomer.code.like(f"{tag}%"))
    products = select(DimProduct.id).where(DimProduct.sku.like(f"{tag}%"))
    rivals = select(DimCompetitorProduct.id).where(DimCompetitorProduct.sku == tag)
    lineup_ids = select(CommercialLineupLine.case_id).where(
        CommercialLineupLine.product_id.in_(products)
    )
    checks = {
        "customers": select(func.count())
        .select_from(DimCustomer)
        .where(DimCustomer.id.in_(customers)),
        "products": select(func.count()).select_from(DimProduct).where(DimProduct.id.in_(products)),
        "distributors": select(func.count())
        .select_from(DimDistributor)
        .where(DimDistributor.code == f"{tag}-D"),
        "brands": select(func.count())
        .select_from(DimCompetitorBrand)
        .where(DimCompetitorBrand.name == tag),
        "rivals": select(func.count())
        .select_from(DimCompetitorProduct)
        .where(DimCompetitorProduct.id.in_(rivals)),
        "lineup_cases": select(func.count())
        .select_from(CommercialLineupCase)
        .where(CommercialLineupCase.id == lineup_id),
    }
    for model, condition in [
        (ST, ST.source_key.like(f"{tag}%")),
        (CommercialLineupLine, CommercialLineupLine.case_id.in_(lineup_ids)),
        (CommercialSkuAssumption, CommercialSkuAssumption.product_id.in_(products)),
        (FactLineupPlanItem, FactLineupPlanItem.product_id.in_(products)),
        (CporCase, CporCase.case_code == tag),
        (CporCaseLine, CporCaseLine.product_id.in_(products)),
        (CustomerListing, CustomerListing.customer_id.in_(customers)),
        (ListingObservation, ListingObservation.listing_id == listing_id),
        (FactDemandForecast, FactDemandForecast.source_key == f"{tag}-FORECAST"),
        (FactCompetitorMapping, FactCompetitorMapping.competitor_product_id.in_(rivals)),
        (FactCompetitorPrice, FactCompetitorPrice.competitor_product_id.in_(rivals)),
        (FactInboundShipment, FactInboundShipment.source_key == f"{tag}-SHIP"),
        (FactBuyPlan, FactBuyPlan.product_id.in_(products)),
        (FactSalesSellout, FactSalesSellout.source_key == f"{tag}-DSI"),
        (WeeksOfCoverObservation, WeeksOfCoverObservation.source_key == f"{tag}-WOC"),
    ]:
        checks[model.__tablename__] = select(func.count()).select_from(model).where(condition)
    counts = await leftover_counts(checks)
    assert all(n == 0 for n in counts.values()), counts


@pytest.mark.anyio
async def test_planner_price_cost_stock_units_ignore_all_decoys(world):
    db, tenant, cid, pid, decoy, _seed = world
    out = await db.run_sync(
        lambda sync: builder.build_promo_plan_draft(
            sync,
            tenant_id=tenant,
            customer_id=cid,
            period_label=PERIOD,
        )
    )
    assert [row["product_id"] for row in out["lines"]] == [pid]
    row = out["lines"][0]
    assert row["srp"] == 250
    assert row["suggested_cost_basis"] == 100
    assert row["volume"]["weekly_run_rate"] == 45
    assert row["volume"]["forecast_units"] == 585
    cover = row["promotion_evidence"]["observed_cover"]
    assert cover["soh_units"] == 180
    assert cover["weeks"] == 4
    assert row["promotion_evidence"]["listing"]["last_observed_price"] is None
    assert row["promotion_evidence"]["competitor_price"]["prices"] == []
    assert out["comparables"]["count"] == 0
    assert out["budget_check"]["tracks"]["money"]["planned_reservation_usd"] is None
    assert decoy not in [r["product_id"] for r in out["lines"]]
    assert (
        await db.run_sync(
            lambda sync: _srp_for_line(sync, customer_id=cid, product_id=pid, tenant_id=tenant)
        )
        == 250
    )


@pytest.mark.anyio
async def test_seed_case_values_are_not_planner_evidence(world):
    db, tenant, cid, pid, decoy, seed = world
    out = await db.run_sync(
        lambda sync: builder.build_promo_plan_draft(
            sync,
            tenant_id=tenant,
            seed_case_id=seed,
            period_label=PERIOD,
        )
    )
    rows = {r["product_id"]: r for r in out["lines"]}
    assert rows[pid]["srp"] == 250
    assert rows[pid]["suggested_cost_basis"] == 100
    assert rows[pid]["volume"]["forecast_units"] == 585
    assert rows[decoy]["srp"] is None
    assert rows[decoy]["suggested_cost_basis"] is None
    assert rows[decoy]["suggested_estimate_qty"] is None
    assert rows[decoy]["missing"]["price"] == st.NO_SELLTHROUGH


@pytest.mark.anyio
async def test_missing_sellthrough_price_cost_do_not_fall_back_to_decoys(world):
    db, tenant, cid, pid, _decoy, _seed = world
    await db.execute(
        update(ST)
        .where(ST.tenant_id == tenant, ST.customer_id == cid)
        .values(
            unit_sell_price=None,
            unit_mac=None,
            unit_cost=None,
        )
    )
    out = await db.run_sync(
        lambda sync: builder.build_promo_plan_draft(
            sync,
            tenant_id=tenant,
            customer_id=cid,
            period_label=PERIOD,
        )
    )
    row = out["lines"][0]
    assert row["srp"] is None and row["missing"]["price"] == st.NO_PRICE
    assert row["suggested_cost_basis"] is None and row["missing"]["cost"] == st.NO_COST
    assert (
        await db.run_sync(
            lambda sync: _srp_for_line(sync, customer_id=cid, product_id=pid, tenant_id=tenant)
        )
        is None
    )


@pytest.mark.anyio
async def test_latest_week_unit_cost_is_used_when_mac_is_missing(world):
    db, tenant, cid, pid, _decoy, _seed = world
    await db.execute(
        update(ST)
        .where(
            ST.tenant_id == tenant,
            ST.customer_id == cid,
            ST.period_start_date == START + timedelta(weeks=8),
        )
        .values(unit_mac=None)
    )
    cost = await db.run_sync(
        lambda sync: suggest_sellthrough_mac(
            sync,
            tenant_id=tenant,
            customer_id=cid,
            product_id=pid,
        )
    )
    assert float(cost.cost_basis) == 120
    assert cost.evidence["field_used"] == "unit_cost"
