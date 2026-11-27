"""W1-B discovery on cip_test only. The fixture rolls back. No live HTTP. No cip writes."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.customer_web_site import CustomerWebSite
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing
from app.models.listing_link import LINK_CONFIRMED, ListingLink
from app.models.listing_site import ListingSite
from app.services.listing_capture.discovery import discover_reporting_customers
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

_EAN = "9990001112228"
_HOST = "https://catalogue.example.test"
_SITE = "catalogue-example"
_PAGE = (
    '<html><script type="application/ld+json">'
    '{"@type":"Product","gtin13":"9990001112228","offers":['
    '{"@type":"Offer","priceCurrency":"ZAR","price":199.00,'
    '"availability":"https://schema.org/InStock","seller":{"name":"North Counter"}},'
    '{"@type":"Offer","priceCurrency":"ZAR","price":210.00,'
    '"availability":"https://schema.org/InStock","seller":{"name":"West Counter"}}'
    "]}</script></html>"
)


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
    url = _sync_url()
    eng = create_engine(url)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"discovery test runs on cip_test only (current_database()={db})")
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


def _confirm_site(
    session: Session,
    *,
    tenant: str,
    customer: DimCustomer,
    site_key: str,
    domain: str,
    search_url_pattern: str | None = None,
    product_url_pattern: str | None = None,
) -> ListingSite:
    """A confirmed web site. listing_seed is not how discovery learns a site."""
    site = ListingSite(
        tenant_id=tenant,
        site_key=site_key,
        display_name=site_key,
        adapter_key="html_page",
        search_url_pattern=search_url_pattern,
        product_url_pattern=product_url_pattern,
    )
    session.add(site)
    session.flush()
    session.add(
        CustomerWebSite(
            tenant_id=tenant,
            customer_id=int(customer.id),
            domain=domain,
            site_id=int(site.id),
            status="confirmed",
            source="steward",
            evidence={},
        )
    )
    session.flush()
    return site


def test_discovery_proposes_a_listing_and_records_a_customer_with_no_site(
    db_session: Session,
) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    assert db == "cip_test"

    tenant = f"t-w1b-{uuid.uuid4().hex[:8]}"
    found = _customer(db_session, tenant, "found")
    missing = _customer(db_session, tenant, "missing")
    product = DimProduct(
        tenant_id=tenant,
        sku=f"sku-{uuid.uuid4().hex[:8]}",
        name="Catalogue item",
        ean=_EAN,
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add_all(
        [
            CustomerReportConfig(
                customer_id=int(found.id),
                reports_expected=True,
                feed_profile_json={},
            ),
            CustomerReportConfig(
                customer_id=int(missing.id), reports_expected=True, feed_profile_json={}
            ),
            FactCustomerSellthrough(
                source_key=f"w1b-{uuid.uuid4().hex}",
                tenant_id=tenant,
                customer_id=int(found.id),
                product_id=int(product.id),
                period_start_date=date(2026, 11, 2),
                period_type="week",
                units_sold=1,
                reported_soh=3,
            ),
        ]
    )
    db_session.flush()
    # Requirement: a site comes from a confirmed web site, not listing_seed.
    _confirm_site(
        db_session,
        tenant=tenant,
        customer=found,
        site_key=_SITE,
        domain="catalogue.example.test",
        search_url_pattern=f"{_HOST}/search?q={{query}}",
        product_url_pattern=f"{_HOST}/p/{{page_id}}",
    )

    def http_get(url: str):
        if "/search" in url:
            return 200, f'<a href="{_HOST}/p/item-{_EAN}">view</a>'
        if url.rstrip("/").endswith(_EAN):
            return 200, _PAGE
        return 404, ""

    report = discover_reporting_customers(db_session, tenant_id=tenant, http_get=http_get)
    by_id = {int(row["customer_id"]): row for row in report["customers"]}
    found_row = by_id[int(found.id)]
    missing_row = by_id[int(missing.id)]

    assert found_row["reason"] is None
    assert found_row["reader"] == "html_page"
    assert found_row["reader_ready"] is True
    assert found_row["proposed_created"] == 1
    assert missing_row["reason"] == "no_site_key"
    assert missing_row["proposed_listings"] == 0

    seed = db_session.scalar(
        select(CstListingSeed).where(
            CstListingSeed.customer_id == int(found.id),
            CstListingSeed.marketplace == _SITE,
            CstListingSeed.status == "proposed",
        )
    )
    assert seed is not None
    assert seed.product_id == product.id
    payload = seed.raw_json or {}
    assert payload["price"] == 199.0
    assert payload["availability"] == "in_stock"
    assert payload["seller"] == "North Counter"
    assert payload["buy_box"] == {
        "price": 199.0,
        "availability": "in_stock",
        "seller": "North Counter",
    }
    assert payload["marketplace_sellers"] == ["North Counter", "West Counter"]
    assert payload["corroboration"] == "barcode"

    site = db_session.scalar(
        select(ListingSite).where(ListingSite.tenant_id == tenant, ListingSite.site_key == _SITE)
    )
    assert site is not None and site.adapter_key == "html_page"
    assert site.product_url_pattern and "{page_id}" in site.product_url_pattern
    link = db_session.scalar(
        select(ListingLink).where(
            ListingLink.site_id == int(site.id),
            ListingLink.product_id == int(product.id),
            ListingLink.status == LINK_CONFIRMED,
        )
    )
    assert link is not None and link.url == payload["url"]
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CustomerListing)
            .where(CustomerListing.customer_id == int(found.id))
        )
        == 0
    )

    again = discover_reporting_customers(db_session, tenant_id=tenant, http_get=http_get)
    again_found = {int(row["customer_id"]): row for row in again["customers"]}[int(found.id)]
    assert again_found["proposed_created"] == 0
    assert again_found["proposed_listings"] == 1
    assert again_found["reader_ready"] is True
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CstListingSeed)
            .where(CstListingSeed.customer_id == int(found.id))
        )
        == 1
    )


def _product(session: Session, tenant: str, *, ean: str, model: str | None = None) -> DimProduct:
    row = DimProduct(
        tenant_id=tenant,
        sku=f"sku-{uuid.uuid4().hex[:8]}",
        name="Catalogue item",
        ean=ean,
        model_name=model,
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row


def _expect(session: Session, customer: DimCustomer, seed: dict | None) -> None:
    session.add(
        CustomerReportConfig(
            customer_id=int(customer.id),
            reports_expected=True,
            feed_profile_json={"listing_seed": seed} if seed is not None else {},
        )
    )


def _stock(
    session: Session,
    *,
    tenant: str,
    customer: DimCustomer,
    product: DimProduct,
    when: date,
    soh: int,
) -> None:
    session.add(
        FactCustomerSellthrough(
            source_key=f"w1b-{uuid.uuid4().hex}",
            tenant_id=tenant,
            customer_id=int(customer.id),
            product_id=int(product.id),
            period_start_date=when,
            period_type="week",
            units_sold=1,
            reported_soh=soh,
        )
    )


def _seed_count(session: Session, customer_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(CstListingSeed)
            .where(CstListingSeed.customer_id == int(customer_id))
        )
        or 0
    )


def test_latest_period_of_zero_stock_does_not_reuse_an_older_period(db_session: Session) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    assert db == "cip_test"
    tenant = f"t-w1b-{uuid.uuid4().hex[:8]}"
    customer = _customer(db_session, tenant, "zero")
    product = _product(db_session, tenant, ean="7770001112226")
    _expect(db_session, customer, None)
    _confirm_site(
        db_session,
        tenant=tenant,
        customer=customer,
        site_key="period-example",
        domain="period.example.test",
        search_url_pattern=f"{_HOST}/search?q={{query}}",
        product_url_pattern=f"{_HOST}/p/{{page_id}}",
    )
    _stock(
        db_session, tenant=tenant, customer=customer, product=product, when=date(2026, 10, 5), soh=8
    )
    _stock(
        db_session, tenant=tenant, customer=customer, product=product, when=date(2026, 11, 9), soh=0
    )
    db_session.flush()

    def http_get(url: str):
        raise AssertionError(url)

    report = discover_reporting_customers(db_session, tenant_id=tenant, http_get=http_get)
    row = {int(item["customer_id"]): item for item in report["customers"]}[int(customer.id)]
    assert row["reason"] == "no_catalogue_products"
    assert row["proposed_listings"] == 0
    assert _seed_count(db_session, int(customer.id)) == 0


def test_confirmed_link_must_still_corroborate_and_be_complete(db_session: Session) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    assert db == "cip_test"
    tenant = f"t-w1b-{uuid.uuid4().hex[:8]}"
    stale = _customer(db_session, tenant, "stale")
    incomplete = _customer(db_session, tenant, "partial")
    stale_product = _product(db_session, tenant, ean=_EAN)
    partial_product = _product(db_session, tenant, ean="6660001112225")
    _expect(db_session, stale, None)
    _expect(db_session, incomplete, None)
    _stock(
        db_session,
        tenant=tenant,
        customer=stale,
        product=stale_product,
        when=date(2026, 11, 2),
        soh=2,
    )
    _stock(
        db_session,
        tenant=tenant,
        customer=incomplete,
        product=partial_product,
        when=date(2026, 11, 2),
        soh=2,
    )
    stale_site = ListingSite(
        tenant_id=tenant, site_key="stale-example", display_name="Stale Example"
    )
    partial_site = ListingSite(
        tenant_id=tenant, site_key="partial-example", display_name="Partial Example"
    )
    db_session.add_all([stale_site, partial_site])
    db_session.flush()
    db_session.add_all(
        [
            CustomerWebSite(
                tenant_id=tenant,
                customer_id=int(stale.id),
                domain="stale.example.test",
                site_id=int(stale_site.id),
                status="confirmed",
                source="steward",
                evidence={},
            ),
            CustomerWebSite(
                tenant_id=tenant,
                customer_id=int(incomplete.id),
                domain="partial.example.test",
                site_id=int(partial_site.id),
                status="confirmed",
                source="steward",
                evidence={},
            ),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            ListingLink(
                tenant_id=tenant,
                site_id=int(stale_site.id),
                product_id=int(stale_product.id),
                url=f"{_HOST}/p/remembered-stale",
                status=LINK_CONFIRMED,
                evidence={},
                decided_by="steward",
            ),
            ListingLink(
                tenant_id=tenant,
                site_id=int(partial_site.id),
                product_id=int(partial_product.id),
                url=f"{_HOST}/p/remembered-partial",
                status=LINK_CONFIRMED,
                evidence={},
                decided_by="steward",
            ),
        ]
    )
    db_session.flush()

    def http_get(url: str):
        if url.endswith("remembered-stale"):
            return 200, "<html><p>a different product</p></html>"
        if url.endswith("remembered-partial"):
            return 200, '<html><script>{"gtin13":"6660001112225"}</script></html>'
        return 404, ""

    report = discover_reporting_customers(db_session, tenant_id=tenant, http_get=http_get)
    by_id = {int(item["customer_id"]): item for item in report["customers"]}
    assert by_id[int(stale.id)]["reason"] == "not_found_on_site"
    assert by_id[int(incomplete.id)]["reason"] == "capture_incomplete"
    assert _seed_count(db_session, int(stale.id)) == 0
    assert _seed_count(db_session, int(incomplete.id)) == 0


def test_search_form_uses_its_own_input_name_and_action(db_session: Session) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    assert db == "cip_test"
    tenant = f"t-w1b-{uuid.uuid4().hex[:8]}"
    host = "https://forms.example.test"
    customer = _customer(db_session, tenant, "forms")
    product = _product(db_session, tenant, ean=_EAN)
    _expect(db_session, customer, None)
    _confirm_site(
        db_session,
        tenant=tenant,
        customer=customer,
        site_key="forms-example",
        domain="forms.example.test",
        product_url_pattern=f"{host}/p/{{page_id}}",
    )
    _stock(
        db_session, tenant=tenant, customer=customer, product=product, when=date(2026, 11, 2), soh=2
    )
    db_session.flush()
    seen: list[str] = []

    def http_get(url: str):
        seen.append(url)
        if url.rstrip("/") == host:
            return 200, (
                '<form action="/decoy"><input name="email"></form>'
                '<form action="/find"><input type="text" name="search"></form>'
            )
        if "/find?" in url and "search=" in url:
            return 200, f'<a href="{host}/p/item-{_EAN}">view</a>'
        if url.rstrip("/").endswith(_EAN):
            return 200, _PAGE
        return 404, ""

    report = discover_reporting_customers(db_session, tenant_id=tenant, http_get=http_get)
    row = {int(item["customer_id"]): item for item in report["customers"]}[int(customer.id)]
    assert row["proposed_created"] == 1
    assert not any("/decoy" in url for url in seen)
    assert any(
        "/find?" in url and "search=" in url and "q=" not in url.split("?", 1)[-1] for url in seen
    )
    site = db_session.scalar(select(ListingSite).where(ListingSite.tenant_id == tenant))
    assert site is not None
    assert site.search_url_pattern == f"{host}/find?search={{query}}"


def test_sitemap_fallback_tries_the_model_as_well_as_the_barcode(db_session: Session) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    assert db == "cip_test"
    tenant = f"t-w1b-{uuid.uuid4().hex[:8]}"
    host = "https://maps.example.test"
    customer = _customer(db_session, tenant, "maps")
    product = _product(db_session, tenant, ean="8880001112227", model="GLIDE14")
    _expect(db_session, customer, None)
    _confirm_site(
        db_session,
        tenant=tenant,
        customer=customer,
        site_key="maps-example",
        domain="maps.example.test",
        product_url_pattern=f"{host}/p/{{page_id}}",
    )
    _stock(
        db_session, tenant=tenant, customer=customer, product=product, when=date(2026, 11, 2), soh=2
    )
    db_session.flush()
    page = (
        '<html><script type="application/ld+json">'
        '{"model":"GLIDE14","offers":[{"priceCurrency":"ZAR","price":188.00,'
        '"availability":"https://schema.org/InStock","seller":{"name":"Map Counter"}}]}'
        "</script></html>"
    )

    def http_get(url: str):
        if url.rstrip("/") == host:
            return 200, "<html>home</html>"
        if url.endswith("/sitemap.xml"):
            return 200, (
                "<urlset>"
                f"<url><loc>{host}/p/other-page</loc></url>"
                f"<url><loc>{host}/p/GLIDE14</loc></url>"
                "</urlset>"
            )
        if url.rstrip("/").endswith("GLIDE14"):
            return 200, page
        return 404, ""

    report = discover_reporting_customers(db_session, tenant_id=tenant, http_get=http_get)
    row = {int(item["customer_id"]): item for item in report["customers"]}[int(customer.id)]
    assert row["reason"] is None
    assert row["proposed_created"] == 1
    seed = db_session.scalar(
        select(CstListingSeed).where(CstListingSeed.customer_id == int(customer.id))
    )
    assert seed is not None
    assert (seed.raw_json or {})["corroboration"] == "model"
    assert (seed.raw_json or {})["price"] == 188.0
    assert "8880001112227" not in str((seed.raw_json or {}).get("url"))
