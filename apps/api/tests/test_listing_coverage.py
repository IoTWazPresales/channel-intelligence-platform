"""Coverage buckets on cip_test only. The fixture rolls back. Never write cip."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing, ListingObservation
from app.models.listing_link import QUEUE_NOT_ON_SITE, QUEUE_OPEN, QUEUE_REJECTED, ListingLinkQueue
from app.models.listing_site import ListingSite
from app.services.listing_capture.autoconfig import capture_health
from app.services.listing_capture.coverage import customer_coverage


def _sync_url() -> str:
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

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
    url = _sync_url()
    eng = create_engine(url)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"listing coverage tests run on cip_test only (current_database()={db})")
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


def _customer(session: Session, tenant: str, label: str) -> DimCustomer:
    tag = uuid.uuid4().hex[:8]
    row = DimCustomer(
        code=f"{label}-{tag}",
        name=f"{label} {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    session.add(row)
    session.flush()
    return row


def _product(session: Session, tenant: str) -> DimProduct:
    tag = uuid.uuid4().hex[:8]
    row = DimProduct(tenant_id=tenant, sku=f"sku-{tag}", name=f"Item {tag}", is_active=True)
    session.add(row)
    session.flush()
    return row


def _sell(session: Session, tenant: str, customer: DimCustomer, product: DimProduct) -> None:
    session.add(
        FactCustomerSellthrough(
            source_key=f"cov-{uuid.uuid4().hex}",
            tenant_id=tenant,
            customer_id=int(customer.id),
            product_id=int(product.id),
            period_start_date=date(2026, 11, 2),
            period_type="week",
            period_grain="week",
            period_week=45,
            period_year=2026,
            units_sold=1,
        )
    )
    session.flush()


def _listing(
    session: Session,
    customer: DimCustomer,
    product: DimProduct,
    *,
    status: str,
    url: str,
    marketplace: str = "shop-a",
) -> CustomerListing:
    row = CustomerListing(
        customer_id=int(customer.id),
        product_id=int(product.id),
        url=url,
        marketplace=marketplace,
        status=status,
        source="manual",
    )
    session.add(row)
    session.flush()
    return row


def _obs(session: Session, listing: CustomerListing, status: str, *, when: datetime) -> None:
    session.add(
        ListingObservation(
            listing_id=int(listing.id),
            fetched_at=when,
            parser_version="test",
            parse_status=status,
        )
    )
    session.flush()


def _queue(session: Session, tenant: str, site: ListingSite, customer: DimCustomer, product: DimProduct, status: str) -> None:
    session.add(
        ListingLinkQueue(
            tenant_id=tenant,
            site_id=int(site.id),
            product_id=int(product.id),
            customer_id=int(customer.id),
            reason="no_match",
            status=status,
        )
    )
    session.flush()


def _row(payload: dict, customer_id: int) -> dict:
    return next(row for row in payload["customers"] if row["customer_id"] == customer_id)


def test_coverage_partitions_each_reported_product_once(db_session: Session) -> None:
    tenant = f"t-cov-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "counter")
    quiet = _customer(db_session, tenant, "quiet")
    db_session.add(CustomerReportConfig(customer_id=int(customer.id), reports_expected=True))
    db_session.add(CustomerReportConfig(customer_id=int(quiet.id), reports_expected=True))
    other = _customer(db_session, f"t-other-{uuid.uuid4().hex[:6]}", "other")
    db_session.add(CustomerReportConfig(customer_id=int(other.id), reports_expected=True))
    db_session.flush()

    watched_ok = _product(db_session, tenant)
    watched_oos = _product(db_session, tenant)
    watched_priority = _product(db_session, tenant)
    failing_parse = _product(db_session, tenant)
    failing_dead = _product(db_session, tenant)
    awaiting = _product(db_session, tenant)
    not_found = _product(db_session, tenant)
    rejected = _product(db_session, tenant)
    untouched = _product(db_session, tenant)
    for product in (
        watched_ok,
        watched_oos,
        watched_priority,
        failing_parse,
        failing_dead,
        awaiting,
        not_found,
        rejected,
        untouched,
    ):
        _sell(db_session, tenant, customer, product)
    other_product = _product(db_session, other.tenant_id)
    _sell(db_session, other.tenant_id, other, other_product)

    now = datetime.now(timezone.utc)
    ok = _listing(db_session, customer, watched_ok, status="active", url=f"https://shop-a.example.test/ok/{watched_ok.id}")
    _obs(db_session, ok, "parse_failed", when=now - timedelta(hours=2))
    _obs(db_session, ok, "ok", when=now)
    _listing(db_session, customer, watched_oos, status="out_of_stock", url=f"https://shop-a.example.test/oos/{watched_oos.id}")
    priority = _listing(
        db_session,
        customer,
        watched_priority,
        status="active",
        url=f"https://shop-a.example.test/both/{watched_priority.id}",
    )
    _obs(db_session, priority, "ok", when=now)
    failed = _listing(
        db_session,
        customer,
        failing_parse,
        status="active",
        url=f"https://shop-a.example.test/fail/{failing_parse.id}",
    )
    _obs(db_session, failed, "ok", when=now - timedelta(hours=2))
    _obs(db_session, failed, "parse_failed", when=now)
    _listing(db_session, customer, failing_dead, status="dead_link", url=f"https://shop-a.example.test/dead/{failing_dead.id}")

    site = ListingSite(tenant_id=tenant, site_key="shop-a", display_name="Shop A", adapter_key="html_page")
    db_session.add(site)
    db_session.flush()
    _queue(db_session, tenant, site, customer, watched_priority, QUEUE_OPEN)
    _queue(db_session, tenant, site, customer, not_found, QUEUE_NOT_ON_SITE)
    _queue(db_session, tenant, site, customer, rejected, QUEUE_REJECTED)
    db_session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"seed-{awaiting.id}",
            product_id=int(awaiting.id),
            status="proposed",
        )
    )
    db_session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"seed-open-{uuid.uuid4().hex[:6]}",
            product_id=None,
            status="proposed",
        )
    )
    db_session.flush()

    payload = customer_coverage(db_session, tenant)
    assert payload["data_unavailable"] is False
    row = _row(payload, int(customer.id))
    assert row["watched"] == 3
    assert row["failing"] == 2
    assert row["awaiting_steward"] == 2
    assert row["not_found"] == 2
    assert row["not_searched"] == 1
    assert row["reported"] == 10
    quiet_row = _row(payload, int(quiet.id))
    assert quiet_row["reported"] == 0
    assert quiet_row["watched"] == 0
    assert quiet_row["not_searched"] == 0
    assert all(item["customer_id"] != int(other.id) for item in payload["customers"])

    health = capture_health(db_session, tenant_id=tenant)
    assert _row(health["coverage"], int(customer.id))["reported"] == 10


def test_coverage_failure_leaves_the_session_usable(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.listing_capture import coverage as coverage_mod

    def boom(session: Session, tenant_id: str) -> dict:
        raise RuntimeError("coverage down")

    monkeypatch.setattr(coverage_mod, "_coverage", boom)
    payload = customer_coverage(db_session, "t-down")
    assert payload == {"data_unavailable": True, "customers": []}
    assert db_session.execute(text("select 1")).scalar_one() == 1


def test_a_site_with_no_reader_is_not_watched(db_session: Session) -> None:
    tenant = f"t-cov-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "counter")
    db_session.add(CustomerReportConfig(customer_id=int(customer.id), reports_expected=True))
    db_session.flush()
    live = _product(db_session, tenant)
    dead = _product(db_session, tenant)
    _sell(db_session, tenant, customer, live)
    _sell(db_session, tenant, customer, dead)
    ok = _listing(db_session, customer, live, status="active", url=f"https://shop-a.example.test/ok/{live.id}")
    _obs(db_session, ok, "ok", when=datetime.now(timezone.utc))
    _listing(db_session, customer, dead, status="dead_link", url=f"https://shop-a.example.test/dead/{dead.id}")
    db_session.add(ListingSite(tenant_id=tenant, site_key="shop-a", display_name="Shop A"))
    db_session.flush()

    row = _row(customer_coverage(db_session, tenant), int(customer.id))
    assert row["watched"] == 0
    assert row["failing"] == 1
    assert row["not_searched"] == 1
    assert row["awaiting_steward"] == 0
    assert row["not_found"] == 0
    assert row["reported"] == 2


def test_watched_matches_site_key_without_case(db_session: Session) -> None:
    tenant = f"t-cov-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "counter")
    db_session.add(CustomerReportConfig(customer_id=int(customer.id), reports_expected=True))
    db_session.flush()
    product = _product(db_session, tenant)
    _sell(db_session, tenant, customer, product)
    listing = _listing(
        db_session,
        customer,
        product,
        status="active",
        url=f"https://shop-a.example.test/ok/{product.id}",
        marketplace="Shop-A",
    )
    _obs(db_session, listing, "ok", when=datetime.now(timezone.utc))
    db_session.add(
        ListingSite(tenant_id=tenant, site_key="shop-a", display_name="Shop A", adapter_key="html_page")
    )
    db_session.flush()

    row = _row(customer_coverage(db_session, tenant), int(customer.id))
    assert row["watched"] == 1
    assert row["not_searched"] == 0


def test_a_rejected_feed_proposal_counts_as_not_found(db_session: Session) -> None:
    tenant = f"t-cov-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "counter")
    db_session.add(CustomerReportConfig(customer_id=int(customer.id), reports_expected=True))
    db_session.flush()
    rejected_product = _product(db_session, tenant)
    both = _product(db_session, tenant)
    _sell(db_session, tenant, customer, rejected_product)
    _sell(db_session, tenant, customer, both)
    db_session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"rej-{rejected_product.id}",
            product_id=int(rejected_product.id),
            status="rejected",
        )
    )
    db_session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"rej-both-{both.id}",
            product_id=int(both.id),
            status="rejected",
        )
    )
    db_session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"prop-both-{both.id}",
            product_id=int(both.id),
            status="proposed",
        )
    )
    db_session.add(
        CstListingSeed(
            customer_id=int(customer.id),
            marketplace="shop-a",
            external_id=f"rej-open-{uuid.uuid4().hex[:6]}",
            product_id=None,
            status="rejected",
        )
    )
    db_session.flush()

    row = _row(customer_coverage(db_session, tenant), int(customer.id))
    assert row["not_found"] == 2
    assert row["awaiting_steward"] == 1
    assert row["not_searched"] == 0
    assert row["watched"] == 0
    assert row["reported"] == 3
