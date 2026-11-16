"""W1-B discovery on cip_test only. The fixture rolls back. No live HTTP. No cip writes."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing
from app.models.listing_link import LINK_CONFIRMED, ListingLink
from app.models.listing_site import ListingSite
from app.services.listing_capture.discovery import discover_reporting_customers

_EAN = "9990001112228"
_HOST = "https://catalogue.example.test"
_SITE = "catalogue-example"
_PAGE = (
    "<html><script type=\"application/ld+json\">"
    '{"@type":"Product","gtin13":"9990001112228","offers":['
    '{"@type":"Offer","priceCurrency":"ZAR","price":199.00,'
    '"availability":"https://schema.org/InStock","seller":{"name":"North Counter"}},'
    '{"@type":"Offer","priceCurrency":"ZAR","price":210.00,'
    '"availability":"https://schema.org/InStock","seller":{"name":"West Counter"}}'
    "]}</script></html>"
)


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


def test_discovery_proposes_a_listing_and_records_a_customer_with_no_site(db_session: Session) -> None:
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
                feed_profile_json={
                    "listing_seed": {
                        "marketplace": _SITE,
                        "site": {"search_url_pattern": f"{_HOST}/search?q={{query}}", "display_name": "Catalogue Example"},
                    }
                },
            ),
            CustomerReportConfig(customer_id=int(missing.id), reports_expected=True, feed_profile_json={}),
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
    assert payload["buy_box"] == {"price": 199.0, "availability": "in_stock", "seller": "North Counter"}
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
