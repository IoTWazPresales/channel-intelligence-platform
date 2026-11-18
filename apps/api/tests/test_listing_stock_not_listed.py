"""In stock, not watched worklist (W1-B) on cip_test only. The fixture rolls back."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing, ListingObservation
from app.models.listing_site import ListingSite
from app.services.listing_capture.stock_not_listed import stock_not_listed
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

LATEST = date(2026, 11, 9)
OLDER = date(2026, 11, 2)


def _sync_url() -> str:
    from app.core.config import get_settings
    from sqlalchemy.engine import make_url

    get_settings.cache_clear()
    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    parsed = make_url(url)
    if (parsed.database or "").casefold() == "cip":
        parsed = parsed.set(database="cip_test")
    return parsed.render_as_string(hide_password=False)


@pytest.fixture()
def db_session():
    eng = create_engine(_sync_url())
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"worklist tests run on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
        eng.dispose()


def _customer(session: Session, tenant: str, *, reporting: bool = True) -> DimCustomer:
    tag = uuid.uuid4().hex[:8]
    row = DimCustomer(
        code=f"acct-{tag}",
        name=f"Account {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    session.add(row)
    session.flush()
    session.add(CustomerReportConfig(customer_id=int(row.id), reports_expected=reporting))
    session.flush()
    return row


def _product(session: Session, tenant: str) -> DimProduct:
    tag = uuid.uuid4().hex[:8]
    row = DimProduct(tenant_id=tenant, sku=f"sku-{tag}", name=f"Item {tag}", is_active=True)
    session.add(row)
    session.flush()
    return row


def _stock(session, tenant, customer, product, soh, *, when=LATEST, site=None) -> None:
    session.add(
        FactCustomerSellthrough(
            source_key=f"snl-{uuid.uuid4().hex}",
            tenant_id=tenant,
            customer_id=int(customer.id),
            product_id=int(product.id),
            period_start_date=when,
            period_type="week",
            period_grain="week",
            period_week=when.isocalendar()[1],
            period_year=when.year,
            units_sold=1,
            reported_soh=soh,
            site_label=site,
        )
    )
    session.flush()


def _listing(session, customer, product, *, status: str) -> CustomerListing:
    row = CustomerListing(
        customer_id=int(customer.id),
        product_id=int(product.id),
        url=f"https://shop-a.example.test/{uuid.uuid4().hex[:8]}",
        marketplace="shop-a",
        status=status,
        source="manual",
    )
    session.add(row)
    session.flush()
    session.add(
        ListingObservation(
            listing_id=int(row.id),
            fetched_at=datetime.now(UTC),
            parser_version="test",
            http_status=200,
            parse_status="ok",
        )
    )
    session.flush()
    return row


def _setup(session: Session):
    tenant = f"t-snl-{uuid.uuid4().hex[:6]}"
    session.add(
        ListingSite(
            tenant_id=tenant, site_key="shop-a", display_name="shop-a", adapter_key="html_page"
        )
    )
    session.flush()
    customer = _customer(session, tenant)
    p = {
        name: _product(session, tenant)
        for name in ("watched", "bare", "zero", "dead", "old", "sites", "seed")
    }
    _stock(session, tenant, customer, p["watched"], 5)
    _listing(session, customer, p["watched"], status="active")
    _stock(session, tenant, customer, p["bare"], 3)
    _stock(session, tenant, customer, p["zero"], 0)
    _stock(session, tenant, customer, p["dead"], 4)
    _listing(session, customer, p["dead"], status="dead_link")
    _stock(session, tenant, customer, p["old"], 9, when=OLDER)
    _stock(session, tenant, customer, p["sites"], 2, site="North")
    _stock(session, tenant, customer, p["sites"], 3, site="South")
    _stock(session, tenant, customer, p["seed"], 1)
    session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"seed-{uuid.uuid4().hex[:6]}",
            product_id=int(p["seed"].id),
            status="proposed",
        )
    )
    session.flush()
    return tenant, customer, p


def test_lists_stocked_products_that_are_not_watched_with_the_reason(db_session: Session) -> None:
    tenant, customer, p = _setup(db_session)
    out = stock_not_listed(db_session, tenant)
    assert out["data_unavailable"] is False
    by_product = {row["product_id"]: row for row in out["rows"]}
    assert set(by_product) == {p["bare"].id, p["dead"].id, p["sites"].id, p["seed"].id}
    assert by_product[p["bare"].id]["coverage"] == "not_searched"
    assert by_product[p["dead"].id]["coverage"] == "failing"
    assert by_product[p["seed"].id]["coverage"] == "awaiting_steward"
    assert by_product[p["sites"].id]["stock_on_hand"] == 5.0
    assert by_product[p["sites"].id]["stock_as_of"] == LATEST.isoformat()
    assert all(row["customer_id"] == customer.id for row in out["rows"])
    assert out["watched_excluded"] == 1
    assert out["total"] == 4 and out["truncated"] is False
    assert out["by_coverage"] == {"not_searched": 2, "failing": 1, "awaiting_steward": 1}
    # Highest stock first within a customer.
    assert [row["stock_on_hand"] for row in out["rows"]] == sorted(
        (row["stock_on_hand"] for row in out["rows"]), reverse=True
    )


def test_scope_limit_and_other_customers(db_session: Session) -> None:
    tenant, customer, p = _setup(db_session)
    quiet = _customer(db_session, tenant, reporting=False)
    _stock(db_session, tenant, quiet, p["bare"], 7)
    other_tenant = f"t-snl-{uuid.uuid4().hex[:6]}"
    stranger = _customer(db_session, other_tenant)
    _stock(db_session, other_tenant, stranger, _product(db_session, other_tenant), 7)

    out = stock_not_listed(db_session, tenant)
    assert {row["customer_id"] for row in out["rows"]} == {customer.id}
    one = stock_not_listed(db_session, tenant, limit=1)
    assert one["total"] == 4 and one["truncated"] is True and len(one["rows"]) == 1
    scoped = stock_not_listed(db_session, tenant, customer_id=int(quiet.id))
    assert scoped["rows"] == [] and scoped["total"] == 0


def test_a_failure_is_reported_not_hidden(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.listing_capture.stock_not_listed as mod

    def boom(*_a, **_k):
        raise RuntimeError("read failed")

    monkeypatch.setattr(mod, "product_buckets", boom)
    out = stock_not_listed(db_session, "any-tenant")
    assert out["data_unavailable"] is True and out["rows"] == []
    assert db_session.execute(text("select 1")).scalar_one() == 1


def test_the_worklist_route_is_a_read_for_any_signed_in_user() -> None:
    from app.api.v1.endpoints.listing_capture import get_stock_not_listed
    from app.main import app

    routes = [
        r
        for r in app.routes
        if getattr(r, "path", "").endswith("/listing-capture/stock-not-listed")
    ]
    assert len(routes) == 1
    assert routes[0].methods == {"GET"}
    assert routes[0].endpoint is get_stock_not_listed
