"""N-0110: customer stock gap against a real database. One rolled-back transaction; cip_test only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.customer_stock_position import CustomerStockPosition
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment
from app.services.channel_intelligence.customer_stock_gap import (
    list_stock_positions,
    recompute_customer_stock_positions,
)

TENANT = "n0110_test"


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


def _ids(db: Session) -> tuple[int, int, int]:
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    other = db.scalar(select(DimCustomer.id).where(DimCustomer.id != customer).order_by(DimCustomer.id).limit(1))
    product = db.scalar(select(DimProduct.id).order_by(DimProduct.id).limit(1))
    if customer is None or other is None or product is None:
        pytest.skip("cip_test needs two customers and a product")
    return int(customer), int(other), int(product)


def _sellthrough(db: Session, customer: int, product: int, start: date, *, units: str, soh: str | None, site: str):
    db.add(
        FactCustomerSellthrough(
            source_key=f"n0110-{customer}-{product}-{start}-{site}",
            tenant_id=TENANT,
            customer_id=customer,
            product_id=product,
            period_start_date=start,
            period_type="weekly",
            period_grain="week",
            period_week=start.isocalendar()[1],
            period_year=start.isocalendar()[0],
            units_sold=Decimal(units),
            reported_soh=Decimal(soh) if soh is not None else None,
            in_transit_units=Decimal("3") if soh is not None else None,
            site_label=site,
        )
    )


def _shipment(db: Session, product: int, pod: date, qty: str, *, customer: int | None, state: str = "shipped"):
    db.add(
        FactInboundShipment(
            tenant_id=TENANT,
            source_key=f"n0110-ship-{product}-{pod}-{qty}-{customer}-{state}",
            report_type="n0110_test",
            line_state=state,
            raw_source_row={},
            quantity=Decimal(qty),
            pod_date=pod,
            product_id=product,
            product_resolution_status="resolved",
            distributor_resolution_status="unresolved",
            resolved_customer_id=customer,
        )
    )


def test_expected_position_and_gap_are_stored_beside_on_hand(session: Session) -> None:
    customer, other, product = _ids(session)
    # Two sites summed per report; week 1 then week 2.
    _sellthrough(session, customer, product, date(2026, 7, 6), units="2", soh="30", site="S1")
    _sellthrough(session, customer, product, date(2026, 7, 6), units="3", soh="10", site="S2")
    _sellthrough(session, customer, product, date(2026, 7, 13), units="6", soh="35", site="S1")
    _sellthrough(session, customer, product, date(2026, 7, 13), units="4", soh="8", site="S2")
    _shipment(session, product, date(2026, 7, 15), "12", customer=customer)  # counts
    _shipment(session, product, date(2026, 7, 15), "50", customer=None)  # no customer match: stays out
    _shipment(session, product, date(2026, 7, 15), "40", customer=other)  # another customer: stays out
    _shipment(session, product, date(2026, 7, 16), "9", customer=customer, state="open")  # not delivered
    session.flush()

    written = recompute_customer_stock_positions(session, tenant_id=TENANT, customer_id=customer, product_ids=[product])
    assert written == 2

    rows = session.scalars(
        select(CustomerStockPosition)
        .where(CustomerStockPosition.tenant_id == TENANT)
        .order_by(CustomerStockPosition.period_end_date)
    ).all()
    assert [r.status for r in rows] == ["first_report", "compared"]
    second = rows[1]
    assert Decimal(second.previous_on_hand) == Decimal("40")
    assert Decimal(second.receipts_units) == Decimal("12")
    assert Decimal(second.units_sold) == Decimal("10")
    assert Decimal(second.expected_on_hand) == Decimal("42")  # 40 + 12 - 10
    assert Decimal(second.reported_on_hand) == Decimal("43")
    assert Decimal(second.gap_units) == Decimal("1")
    assert Decimal(second.in_transit_units) == Decimal("6")

    # The reported on-hand on the fact rows is untouched.
    sohs = session.scalars(
        select(FactCustomerSellthrough.reported_soh).where(FactCustomerSellthrough.tenant_id == TENANT)
    ).all()
    assert sorted(Decimal(s) for s in sohs) == [Decimal("8"), Decimal("10"), Decimal("30"), Decimal("35")]

    listed = list_stock_positions(session, tenant_id=TENANT, threshold_units=1)
    compared = [r for r in listed if r["status"] == "compared"]
    assert compared[0]["gap_units"] == 1.0 and compared[0]["highlighted"] is True
    assert "Over:" in compared[0]["reason"]
    # The 50 shipped with no customer match is a data gap, so the row is not read as stock.
    assert compared[0]["gap_cause"] == "unmatched_shipment"
    assert compared[0]["reason"].startswith("Not read as the customer's stock")
    assert list_stock_positions(session, tenant_id=TENANT, threshold_units=2, highlighted_only=True) == []

    # Recompute replaces, never duplicates.
    recompute_customer_stock_positions(session, tenant_id=TENANT, customer_id=customer, product_ids=[product])
    assert (
        session.scalar(
            select(text("count(*)")).select_from(CustomerStockPosition).where(CustomerStockPosition.tenant_id == TENANT)
        )
        == 2
    )
