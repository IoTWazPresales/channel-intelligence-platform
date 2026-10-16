"""N-0110: why a stock gap differs, against a real database. One rolled-back transaction; cip_test only."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment
from app.services.channel_intelligence.customer_stock_gap import (
    list_stock_positions,
    recompute_customer_stock_positions,
)

TENANT = "n0110_cause"
W1 = date(2026, 7, 6)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(text("select to_regclass('customer_stock_position')")).scalar():
            pytest.skip("20261014_0037 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _ids(db: Session, n_products: int) -> tuple[int, list[int]]:
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    products = list(db.scalars(select(DimProduct.id).order_by(DimProduct.id).limit(n_products)).all())
    if customer is None or len(products) < n_products:
        pytest.skip("cip_test needs a customer and products")
    return int(customer), [int(p) for p in products]


def _row(db: Session, customer: int, product: int, start: date, units: str, soh: str | None, site: str = "S1") -> None:
    db.add(
        FactCustomerSellthrough(
            source_key=f"ct:{customer}:sl:{site}:{product}:{start.isoformat()}",
            tenant_id=TENANT,
            customer_id=customer,
            product_id=product,
            period_start_date=start,
            period_type="weekly",
            period_grain="week",
            units_sold=Decimal(units),
            reported_soh=Decimal(soh) if soh is not None else None,
            site_label=site,
        )
    )


def _ship(db: Session, product: int, qty: str, *, customer: int | None, pod: date | None, landed: date | None = None) -> None:
    db.add(
        FactInboundShipment(
            tenant_id=TENANT,
            source_key=f"n0110-cause-{product}-{qty}-{customer}-{pod}-{landed}",
            report_type="n0110_test",
            line_state="shipped",
            raw_source_row={},
            quantity=Decimal(qty),
            pod_date=pod,
            est_pod_date=landed,
            product_id=product,
            product_resolution_status="resolved",
            distributor_resolution_status="unresolved",
            resolved_customer_id=customer,
        )
    )


def _causes(db: Session, customer: int, products: list[int]) -> dict[tuple[int, str], list[str]]:
    """Causes per (product, report period start) for highlighted compared rows."""
    recompute_customer_stock_positions(db, tenant_id=TENANT, customer_id=customer, product_ids=products)
    rows = list_stock_positions(db, tenant_id=TENANT, threshold_units=1)
    return {
        (r["product_id"], r["period_start_date"]): r["gap_causes"]
        for r in rows
        if r["status"] == "compared" and r["highlighted"]
    }


def test_each_data_gap_is_named_and_only_the_rest_is_unexplained(session: Session) -> None:
    customer, (p_unmatched, p_nopod, p_site, p_unexpl) = _ids(session, 4)
    w2 = W1 + timedelta(days=7)
    # Unmatched shipment: on-hand rose by 10 with nothing matched; 10 shipped to nobody.
    _row(session, customer, p_unmatched, W1, "0", "5")
    _row(session, customer, p_unmatched, w2, "0", "15")
    _ship(session, p_unmatched, "10", customer=None, pod=w2 + timedelta(days=1))
    # No POD: matched to the customer, shipped, but no proof-of-delivery date.
    _row(session, customer, p_nopod, W1, "0", "5")
    _row(session, customer, p_nopod, w2, "0", "9")
    _ship(session, p_nopod, "4", customer=customer, pod=None, landed=w2 + timedelta(days=2))
    # A second site starts reporting on-hand: no previous on-hand for it.
    _row(session, customer, p_site, W1, "0", "5", site="S1")
    _row(session, customer, p_site, w2, "0", "5", site="S1")
    _row(session, customer, p_site, w2, "0", "7", site="S2")
    # A real difference: 3 short, every week reported, nothing else wrong.
    _row(session, customer, p_unexpl, W1, "1", "10")
    _row(session, customer, p_unexpl, w2, "2", "5")
    session.flush()

    causes = _causes(session, customer, [p_unmatched, p_nopod, p_site, p_unexpl])
    at = w2.isoformat()
    assert causes[(p_unmatched, at)] == ["unmatched_shipment"]
    assert causes[(p_nopod, at)] == ["no_pod"]
    assert causes[(p_site, at)] == ["no_prior_on_hand"]
    assert causes[(p_unexpl, at)] == ["unexplained"]
    rows = {
        r["product_id"]: r
        for r in list_stock_positions(session, tenant_id=TENANT, threshold_units=1)
        if r["status"] == "compared"
    }
    assert rows[p_unexpl]["gap_units"] == -3.0  # the number is not changed
    assert rows[p_unmatched]["reason"].startswith("Not read as the customer's stock")
    assert not rows[p_unexpl]["reason"].startswith("Not read")


def test_repeated_report_and_unreported_weeks(session: Session) -> None:
    customer, (p_rep, p_gap) = _ids(session, 2)
    w2 = W1 + timedelta(days=7)
    later = W1 + timedelta(days=35)
    # The same figures loaded for W1 and w2 (every product of the customer).
    _row(session, customer, p_rep, W1, "4", "20")
    _row(session, customer, p_rep, w2, "4", "20")
    _row(session, customer, p_gap, W1, "1", "30")
    _row(session, customer, p_gap, w2, "1", "30")
    # p_gap: next report five weeks later, one week of sales reported in a 4-week window.
    _row(session, customer, p_gap, later, "2", "10")
    session.flush()

    causes = _causes(session, customer, [p_rep, p_gap])
    assert causes[(p_rep, w2.isoformat())] == ["repeated_report"]
    assert causes[(p_gap, w2.isoformat())] == ["repeated_report"]
    # N-0111: three weeks between the reports with neither on-hand nor sales; the chain starts fresh
    # at `later` (unreported weeks), so it is not compared and has no cause. No filler rows.
    assert (p_gap, later.isoformat()) not in causes
    rows = list_stock_positions(session, tenant_id=TENANT, threshold_units=1, product_id=p_gap)
    by_start = {r["period_start_date"]: r for r in rows}
    assert by_start[later.isoformat()]["status"] == "chain_restart"
    assert by_start[later.isoformat()]["reason"].startswith("Unreported weeks")
    assert not [d for d, r in by_start.items() if r["status"] == "no_on_hand"]


def test_missing_on_hand_weeks_with_sales_are_bridged_and_stock_only_rows_are_not_sales(session: Session) -> None:
    customer, (p_bridge, p_stock_only) = _ids(session, 2)
    w2 = W1 + timedelta(days=7)
    w3 = W1 + timedelta(days=14)
    w4 = W1 + timedelta(days=21)
    # p_bridge: on-hand 30, two sales-only weeks (4 and 6), then on-hand 20 = 30 - 4 - 6 (no gap).
    _row(session, customer, p_bridge, W1, "0", "30")
    _row(session, customer, p_bridge, w2, "4", None)
    _row(session, customer, p_bridge, w3, "6", None)
    _row(session, customer, p_bridge, w4, "0", "20")
    # p_stock_only: a stock-only load for w2 stores units 0 with no units figure: not a sales week.
    _row(session, customer, p_stock_only, W1, "0", "30")
    _row(session, customer, p_stock_only, w3, "0", "30")
    stock_only = FactCustomerSellthrough(
        source_key=f"ct:{customer}:sl:S1:{p_stock_only}:{w2.isoformat()}:so",
        tenant_id=TENANT,
        customer_id=customer,
        product_id=p_stock_only,
        period_start_date=w2,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal("0"),
        reported_soh=None,
        site_label="S1",
        figure_import_jobs={"in_transit_units": 1},
    )
    session.add(stock_only)
    session.flush()

    recompute_customer_stock_positions(session, tenant_id=TENANT, customer_id=customer, product_ids=[p_bridge, p_stock_only])
    rows = list_stock_positions(session, tenant_id=TENANT, threshold_units=1)
    bridge = {r["period_start_date"]: r for r in rows if r["product_id"] == p_bridge}
    assert bridge[w2.isoformat()]["status"] == "no_on_hand" and bridge[w3.isoformat()]["status"] == "no_on_hand"
    assert bridge[w4.isoformat()]["status"] == "compared"
    assert bridge[w4.isoformat()]["previous_on_hand"] == 30.0
    assert bridge[w4.isoformat()]["expected_on_hand"] == 20.0 and bridge[w4.isoformat()]["gap_units"] == 0.0
    # w3 has on-hand here, so w2 is the only week between: a row with no units figure leaves it unreported.
    stock = {r["period_start_date"]: r for r in rows if r["product_id"] == p_stock_only}
    assert stock[w3.isoformat()]["status"] == "chain_restart"
