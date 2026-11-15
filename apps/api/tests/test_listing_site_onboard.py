"""Steward site onboarding for a reporting customer with no site key. cip_test only.

One rolled-back transaction. No live HTTP. No named retailer.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.listing_capture.autoconfig import autoconfigure_sites
from app.services.listing_capture.site_onboarding import SiteOnboardError, normalize_domain, record_customer_site

_URLS = [
    "https://shop-a.example.test/p/111",
    "https://shop-a.example.test/p/222",
]


def _sync_url() -> str:
    """Point the sync URL at cip_test when settings still name cip. Never print the URL."""
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
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    print("current_database()", db)
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"stop: site onboarding runs on cip_test only (current_database()={db})")
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


def _customer(session: Session, tenant: str) -> DimCustomer:
    tag = uuid.uuid4().hex[:8]
    row = DimCustomer(
        code=f"cust-{tag}",
        name=f"Counter {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    session.add(row)
    session.flush()
    return row


def _report(session: Session, customer: DimCustomer, seed: dict | None = None, *, expected: bool = True) -> None:
    session.add(
        CustomerReportConfig(
            customer_id=int(customer.id),
            reports_expected=expected,
            feed_profile_json={"listing_seed": seed} if seed is not None else None,
        )
    )
    session.flush()


def _listing(session: Session, customer: DimCustomer, site_key: str) -> None:
    session.add(
        CustomerListing(
            customer_id=int(customer.id),
            url=f"https://{site_key}.example.test/p/1",
            marketplace=site_key,
            status="active",
            source="manual",
        )
    )
    session.flush()


def _site(session: Session, tenant: str, site_key: str) -> ListingSite:
    row = session.scalar(
        select(ListingSite)
        .where(ListingSite.tenant_id == tenant, ListingSite.site_key == site_key)
        .options(selectinload(ListingSite.sellers))
    )
    assert isinstance(row, ListingSite)
    return row


def test_domain_rejects_a_url() -> None:
    with pytest.raises(SiteOnboardError) as caught:
        normalize_domain("https://shop-a.example.test/p/1")
    assert caught.value.code == "domain_invalid"


def test_onboard_records_domain_and_derives_pattern_without_a_seller(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CIP_LISTING_LIVE_FETCH", raising=False)
    tenant = f"t-on-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, None)
    before = autoconfigure_sites(db_session, tenant_id=tenant, http_get=lambda url, headers=None: (_ for _ in ()).throw(AssertionError(url)))
    assert any(row["reason"] == "no_site_key" and row["customer_id"] == customer.id for row in before["excluded"])

    result = record_customer_site(
        db_session,
        tenant_id=tenant,
        customer_id=int(customer.id),
        site_key="Shop-A",
        domain="Shop-A.Example.Test",
        example_urls=_URLS,
        actor="steward@example.test",
    )
    assert result["site_key"] == "shop-a"
    assert result["domain"] == "shop-a.example.test"
    assert result["created_site"] is True
    assert result["pattern_status"] == "derived"
    assert result["product_url_pattern"] == "https://shop-a.example.test/p/{page_id}"

    site = _site(db_session, tenant, "shop-a")
    assert site.first_party_seller is None
    assert site.sellers == []
    assert site.display_name == "shop-a.example.test"
    db_session.refresh(customer)
    config = db_session.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer.id))
    assert isinstance(config, CustomerReportConfig)
    seed = config.feed_profile_json["listing_seed"]
    assert seed["marketplace"] == "shop-a"
    assert seed["site"]["domain"] == "shop-a.example.test"
    assert seed["site"]["example_urls"] == _URLS
    assert "seller_names" not in seed

    again = record_customer_site(
        db_session,
        tenant_id=tenant,
        customer_id=int(customer.id),
        site_key="shop-a",
        domain="shop-a.example.test",
        example_urls=_URLS,
        actor="steward@example.test",
    )
    assert again["created_site"] is False
    assert again["pattern_status"] == "kept"
    assert db_session.scalar(
        select(func.count()).select_from(ListingSite).where(ListingSite.tenant_id == tenant, ListingSite.site_key == "shop-a")
    ) == 1

    after = autoconfigure_sites(db_session, tenant_id=tenant, http_get=lambda url, headers=None: (_ for _ in ()).throw(AssertionError(url)))
    assert all(row["reason"] != "no_site_key" or row["customer_id"] != customer.id for row in after["excluded"])


def test_onboard_keeps_a_pattern_already_on_the_site(db_session: Session) -> None:
    tenant = f"t-keep-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, None)
    kept = "https://shop-a.example.test/kept/{page_id}"
    page_id = r"^https://shop-a\.example\.test/kept/([^/]+)$"
    db_session.add(
        ListingSite(
            tenant_id=tenant,
            site_key="shop-a",
            display_name="kept label",
            product_url_pattern=kept,
            page_id_pattern=page_id,
        )
    )
    db_session.flush()
    result = record_customer_site(
        db_session,
        tenant_id=tenant,
        customer_id=int(customer.id),
        site_key="shop-a",
        domain="shop-a.example.test",
        example_urls=_URLS,
        actor="steward@example.test",
    )
    assert result["pattern_status"] == "kept"
    assert result["created_site"] is False
    site = _site(db_session, tenant, "shop-a")
    assert site.product_url_pattern == kept
    assert site.page_id_pattern == page_id
    assert site.display_name == "kept label"


def test_onboard_refuses_a_customer_that_already_has_a_site_key(db_session: Session) -> None:
    tenant = f"t-has-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, {"marketplace": "shop-b"})
    with pytest.raises(SiteOnboardError) as caught:
        record_customer_site(
            db_session,
            tenant_id=tenant,
            customer_id=int(customer.id),
            site_key="shop-a",
            domain="shop-a.example.test",
            example_urls=None,
            actor="steward@example.test",
        )
    assert caught.value.code == "site_already_recorded"
    config = db_session.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer.id))
    assert config.feed_profile_json["listing_seed"]["marketplace"] == "shop-b"


def test_onboard_refuses_two_listing_marketplaces(db_session: Session) -> None:
    tenant = f"t-two-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, None)
    _listing(db_session, customer, "shop-a")
    _listing(db_session, customer, "shop-b")
    with pytest.raises(SiteOnboardError) as caught:
        record_customer_site(
            db_session,
            tenant_id=tenant,
            customer_id=int(customer.id),
            site_key="shop-a",
            domain="shop-a.example.test",
            example_urls=None,
            actor="steward@example.test",
        )
    assert caught.value.code == "site_already_recorded"


def test_onboard_refuses_a_link_on_another_host(db_session: Session) -> None:
    tenant = f"t-host-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, None)
    with pytest.raises(SiteOnboardError) as caught:
        record_customer_site(
            db_session,
            tenant_id=tenant,
            customer_id=int(customer.id),
            site_key="shop-a",
            domain="shop-a.example.test",
            example_urls=["https://other.example.test/p/1"],
            actor="steward@example.test",
        )
    assert caught.value.code == "url_host_mismatch"
    assert db_session.scalar(select(func.count()).select_from(ListingSite).where(ListingSite.tenant_id == tenant)) == 0


def test_onboard_refuses_a_customer_that_is_not_reporting(db_session: Session) -> None:
    tenant = f"t-nr-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, None, expected=False)
    with pytest.raises(SiteOnboardError) as caught:
        record_customer_site(
            db_session,
            tenant_id=tenant,
            customer_id=int(customer.id),
            site_key="shop-a",
            domain="shop-a.example.test",
            example_urls=None,
            actor="steward@example.test",
        )
    assert caught.value.code == "not_reporting"


def test_onboard_refuses_another_tenants_customer(db_session: Session) -> None:
    customer = _customer(db_session, f"t-other-{uuid.uuid4().hex[:6]}")
    _report(db_session, customer, None)
    with pytest.raises(SiteOnboardError) as caught:
        record_customer_site(
            db_session,
            tenant_id=f"t-caller-{uuid.uuid4().hex[:6]}",
            customer_id=int(customer.id),
            site_key="shop-a",
            domain="shop-a.example.test",
            example_urls=None,
            actor="steward@example.test",
        )
    assert caught.value.code == "customer_not_found"


def test_onboard_refuses_a_different_domain_on_the_second_call(db_session: Session) -> None:
    tenant = f"t-dom-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant)
    _report(db_session, customer, None)
    record_customer_site(
        db_session,
        tenant_id=tenant,
        customer_id=int(customer.id),
        site_key="shop-a",
        domain="shop-a.example.test",
        example_urls=None,
        actor="steward@example.test",
    )
    with pytest.raises(SiteOnboardError) as caught:
        record_customer_site(
            db_session,
            tenant_id=tenant,
            customer_id=int(customer.id),
            site_key="shop-a",
            domain="other.example.test",
            example_urls=None,
            actor="steward@example.test",
        )
    assert caught.value.code == "domain_already_recorded"
