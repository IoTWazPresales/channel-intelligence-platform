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


def test_shared_stock_positions_preserve_latest_dates_and_net_site_totals(db_session: Session) -> None:
    """B2: use the overview's stock reader with each account's own latest stock date."""
    from app.services.channel_intelligence.sell_through_overview import (
        OverviewFilters,
        load_stock_positions,
    )
    from app.services.listing_capture.stock_not_listed import _latest_stock

    tenant = f"t-snl-{uuid.uuid4().hex[:6]}"
    current = _customer(db_session, tenant)
    older = _customer(db_session, tenant)
    zero_only = _customer(db_session, tenant)
    products = {
        name: _product(db_session, tenant)
        for name in ("positive", "net_zero", "negative", "old_only")
    }
    _stock(db_session, tenant, current, products["positive"], 4, site="site-one")
    _stock(db_session, tenant, current, products["positive"], -1, site="site-two")
    _stock(db_session, tenant, current, products["net_zero"], 4, site="site-one")
    _stock(db_session, tenant, current, products["net_zero"], -4, site="site-two")
    _stock(db_session, tenant, current, products["negative"], -2)
    _stock(db_session, tenant, current, products["old_only"], 50, when=OLDER)
    # A newer sales-only row must not move this account's stock date.
    _stock(db_session, tenant, current, products["positive"], None, when=date(2026, 11, 16))
    _stock(db_session, tenant, older, products["positive"], 7, when=OLDER)
    _stock(db_session, tenant, zero_only, products["positive"], 20, when=OLDER)
    _stock(db_session, tenant, zero_only, products["positive"], 0)
    foreign_tenant = f"t-snl-{uuid.uuid4().hex[:6]}"
    foreign = _customer(db_session, foreign_tenant)
    _stock(db_session, foreign_tenant, foreign, _product(db_session, foreign_tenant), 100)

    customer_ids = [int(current.id), int(older.id), int(zero_only.id)]
    filters = OverviewFilters(
        date_from=date.min, date_to=date.max, customer_ids=customer_ids, tenant_id=tenant
    )
    positions, dates = load_stock_positions(db_session, filters, date.max)
    expected = {
        (int(current.id), int(products["positive"].id)): (LATEST, 3.0),
        (int(older.id), int(products["positive"].id)): (OLDER, 7.0),
    }
    assert dates == {current.id: LATEST, older.id: OLDER, zero_only.id: LATEST}
    assert positions[(current.id, products["net_zero"].id)]["soh"] == 0
    assert positions[(current.id, products["negative"].id)]["soh"] == -2
    assert _latest_stock(db_session, tenant, customer_ids) == expected

    out = stock_not_listed(db_session, tenant)
    assert out["data_unavailable"] is False and out["total"] == 2
    assert {
        (row["customer_id"], row["product_id"]): (row["stock_as_of"], row["stock_on_hand"])
        for row in out["rows"]
    } == {key: (when.isoformat(), units) for key, (when, units) in expected.items()}
    for excluded in (zero_only, foreign):
        scoped = stock_not_listed(db_session, tenant, customer_id=int(excluded.id))
        assert scoped["data_unavailable"] is False
        assert scoped["rows"] == [] and scoped["total"] == 0


def test_account_filter_reaches_an_account_omitted_by_the_tenant_limit(db_session: Session) -> None:
    """B1: an earlier account can fill the tenant page without hiding later accounts."""
    tenant, first, products = _setup(db_session)
    first.name = "A first account"
    later = _customer(db_session, tenant)
    later.name = "Z later account"
    # This product is watched for the first account, but not for the later account.
    _stock(db_session, tenant, later, products["watched"], 99)
    db_session.flush()

    all_accounts = stock_not_listed(db_session, tenant, limit=4)
    assert all_accounts["total"] == 5 and all_accounts["truncated"] is True
    assert {row["customer_id"] for row in all_accounts["rows"]} == {first.id}

    scoped = stock_not_listed(db_session, tenant, customer_id=int(later.id), limit=4)
    assert scoped["data_unavailable"] is False
    assert scoped["total"] == 1 and scoped["truncated"] is False
    assert scoped["watched_excluded"] == 0
    assert scoped["by_coverage"] == {"not_searched": 1}
    row = scoped["rows"][0]
    assert row["customer_id"] == later.id and row["product_id"] == products["watched"].id
    assert row["stock_on_hand"] == 99.0 and row["stock_as_of"] == LATEST.isoformat()

    foreign_tenant = f"t-snl-{uuid.uuid4().hex[:6]}"
    foreign = _customer(db_session, foreign_tenant)
    _stock(db_session, foreign_tenant, foreign, _product(db_session, foreign_tenant), 100)
    refused = stock_not_listed(db_session, tenant, customer_id=int(foreign.id))
    assert refused["data_unavailable"] is False
    assert refused["rows"] == [] and refused["total"] == 0
