"""Own-seller auto-fill on a reporting customer's own site (cip_test only, no live HTTP).

Warren's model: a flagged reporting customer is a monitored site. On that site the customer's
own seller is the site's first-party seller, filled by discovery, never hand-typed. A buy-box
held by anyone else on the customer's own site is competition.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.listing_capture import sites as site_service
from app.services.listing_capture.autoconfig import AUTOCONFIG_ACTOR, autoconfigure_sites, capture_health

_EAN = "4006381333931"


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
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
        pytest.skip(f"own-seller tests run on cip_test only (current_database()={db})")
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
    row = DimCustomer(code=f"{label}-{tag}", name=f"{label} {tag}", customer_status="active", is_key_account=False, tenant_id=tenant)
    session.add(row)
    session.flush()
    return row


def _report(session: Session, customer: DimCustomer, seed: dict | None) -> None:
    session.add(
        CustomerReportConfig(
            customer_id=int(customer.id),
            reports_expected=True,
            feed_profile_json={"listing_seed": seed} if seed is not None else None,
        )
    )
    session.flush()


def _product(session: Session, tenant: str) -> DimProduct:
    tag = uuid.uuid4().hex[:8]
    row = DimProduct(tenant_id=tenant, sku=f"sku-{tag}", name=f"Item {tag}", ean=_EAN, is_active=True)
    session.add(row)
    session.flush()
    return row


def _listing(session: Session, customer: DimCustomer, *, site_key: str, url: str, product: DimProduct | None = None) -> CustomerListing:
    row = CustomerListing(
        customer_id=int(customer.id),
        product_id=int(product.id) if product is not None else None,
        url=url,
        marketplace=site_key,
        status="active",
        source="manual",
    )
    session.add(row)
    session.flush()
    return row


def _site(session: Session, tenant: str, site_key: str) -> ListingSite:
    site_id = session.scalar(
        text("select id from listing_site where tenant_id = :t and site_key = :k"), {"t": tenant, "k": site_key}
    )
    assert site_id is not None
    row = session.get(ListingSite, int(site_id))
    assert row is not None
    session.refresh(row)
    return row


def _no_fetch(url, headers=None):
    raise AssertionError(f"unexpected fetch {url}")


def _all_entries(report: dict) -> list[dict]:
    return [row for key in ("configured", "excluded", "needs_pattern") for row in report[key]]


def test_seed_named_site_fills_the_customer_seller_from_the_first_party_seller(db_session: Session) -> None:
    tenant = f"t-own-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "own")
    _report(
        db_session,
        customer,
        {"marketplace": "shop-a", "site": {"adapter_key": "html_page", "first_party_seller": "Shop A Retail"}},
    )
    _listing(db_session, customer, site_key="shop-a", url="https://shop-a.example.test/p/1")

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=_no_fetch)

    assert [row["customer_id"] for row in report["configured"]] == [customer.id]
    assert report["excluded"] == []
    site = _site(db_session, tenant, "shop-a")
    assert [(s.customer_id, list(s.seller_names), list(s.seller_ids), s.updated_by) for s in site.sellers] == [
        (customer.id, ["Shop A Retail"], [], AUTOCONFIG_ACTOR)
    ]
    config = site_service.site_config_from_row(site)
    assert config.is_own_seller(customer.id, name="shop a retail") is True
    # A marketplace seller holding the buy-box on the customer's own site is competition.
    assert config.is_own_seller(customer.id, name="Some Marketplace Trader") is False


def test_steward_first_party_seller_on_the_customers_only_site_is_used(db_session: Session) -> None:
    tenant = f"t-sole-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "sole")
    site_service.create_site(
        db_session,
        tenant_id=tenant,
        site_key="shop-b",
        fields={"display_name": "Shop B", "adapter_key": "html_page", "first_party_seller": "Shop B Direct"},
        actor="steward@x",
    )
    _report(db_session, customer, None)
    _listing(db_session, customer, site_key="shop-b", url="https://shop-b.example.test/p/1")

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=_no_fetch)

    assert [row["customer_id"] for row in report["configured"]] == [customer.id]
    site = _site(db_session, tenant, "shop-b")
    assert [(s.customer_id, list(s.seller_names), s.updated_by) for s in site.sellers] == [
        (customer.id, ["Shop B Direct"], AUTOCONFIG_ACTOR)
    ]
    assert site.first_party_seller == "Shop B Direct"
    assert site.updated_by == "steward@x"


def test_a_site_two_reporting_customers_list_on_is_not_auto_filled(db_session: Session) -> None:
    tenant = f"t-shared-{uuid.uuid4().hex[:6]}"
    first = _customer(db_session, tenant, "first")
    second = _customer(db_session, tenant, "second")
    site_service.create_site(
        db_session,
        tenant_id=tenant,
        site_key="shop-c",
        fields={"display_name": "Shop C", "adapter_key": "html_page", "first_party_seller": "Shop C Retail"},
        actor="steward@x",
    )
    _report(db_session, first, None)
    _report(db_session, second, None)
    _listing(db_session, first, site_key="shop-c", url="https://shop-c.example.test/p/1")
    _listing(db_session, second, site_key="shop-c", url="https://shop-c.example.test/p/2")

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=_no_fetch)

    reasons = {row["customer_id"]: row["reasons"] for row in _all_entries(report)}
    assert reasons[first.id] == ["no_seller_data"]
    assert reasons[second.id] == ["no_seller_data"]
    assert _site(db_session, tenant, "shop-c").sellers == []


def test_seed_seller_names_win_over_the_first_party_seller(db_session: Session) -> None:
    tenant = f"t-seedwin-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "seedwin")
    _report(
        db_session,
        customer,
        {
            "marketplace": "shop-d",
            "seller_names": ["Seeded Name"],
            "site": {"adapter_key": "html_page", "first_party_seller": "Shop D Retail"},
        },
    )
    autoconfigure_sites(db_session, tenant_id=tenant, http_get=_no_fetch)
    site = _site(db_session, tenant, "shop-d")
    assert [list(s.seller_names) for s in site.sellers] == [["Seeded Name"]]


def test_capture_health_counts_the_first_party_seller_without_writing(db_session: Session) -> None:
    tenant = f"t-health-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "health")
    site_service.create_site(
        db_session,
        tenant_id=tenant,
        site_key="shop-e",
        fields={"display_name": "Shop E", "adapter_key": "html_page", "first_party_seller": "Shop E Retail"},
        actor="steward@x",
    )
    _report(db_session, customer, {"marketplace": "shop-e"})

    health = capture_health(db_session, tenant_id=tenant)

    assert [row["customer_id"] for row in health["configured"]] == [customer.id]
    assert health["exclusions"] == []
    assert _site(db_session, tenant, "shop-e").sellers == []


def test_html_probe_learns_the_first_party_seller_from_the_corroborated_page(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")
    tenant = f"t-probe-{uuid.uuid4().hex[:6]}"
    product = _product(db_session, tenant)
    customer = _customer(db_session, tenant, "probe")
    _report(db_session, customer, {"marketplace": "shop-f", "site": {"rate_limit_seconds": 0}})
    _listing(db_session, customer, site_key="shop-f", url="https://shop-f.example.test/p/1", product=product)
    page = (
        '<script type="application/ld+json">{"@type":"Product","gtin13":"' + _EAN + '",'
        '"offers":{"@type":"Offer","priceCurrency":"ZAR","price":1999,'
        '"seller":{"@type":"Organization","name":"Shop F Retail"},'
        '"availability":"https://schema.org/InStock"}}</script>'
    )

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=lambda url, headers=None: (200, page))

    assert [row["customer_id"] for row in report["configured"]] == [customer.id]
    site = _site(db_session, tenant, "shop-f")
    assert site.adapter_key == "html_page"
    assert site.first_party_seller == "Shop F Retail"
    assert [(list(s.seller_names), s.updated_by) for s in site.sellers] == [(["Shop F Retail"], AUTOCONFIG_ACTOR)]


def test_a_page_naming_two_sellers_does_not_set_the_first_party_seller(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")
    tenant = f"t-two-{uuid.uuid4().hex[:6]}"
    product = _product(db_session, tenant)
    customer = _customer(db_session, tenant, "two")
    _report(db_session, customer, {"marketplace": "shop-g"})
    _listing(db_session, customer, site_key="shop-g", url="https://shop-g.example.test/p/1", product=product)
    page = (
        '{"gtin13":"' + _EAN + '","offers":[{"priceCurrency":"ZAR","price":1999,'
        '"seller":{"@type":"Organization","name":"One Seller"}},'
        '{"priceCurrency":"ZAR","price":2099,"seller":{"@type":"Organization","name":"Another Seller"}}]}'
    )

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=lambda url, headers=None: (200, page))

    site = _site(db_session, tenant, "shop-g")
    assert site.first_party_seller is None
    assert site.sellers == []
    reasons = {row["customer_id"]: row["reasons"] for row in _all_entries(report)}
    assert reasons[customer.id] == ["no_seller_data"]
