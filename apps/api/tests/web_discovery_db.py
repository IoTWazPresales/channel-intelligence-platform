"""Database helpers for the Discovery V2 tests. cip_test only: every test skips on any other database.

Two ways to get a world:

- ``outer_tx_session`` runs inside a transaction that is rolled back at the end (Apply tests; Apply
  commits its session, which only releases a savepoint here).
- ``committed_world`` commits real rows under a unique tenant and deletes them afterwards (the
  Preview and API tests, which open their own sessions like the worker and the API do).

Everything is synthetic: invented names, ``.test`` hosts, a made-up country.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import CustomerContact, DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem
from app.models.listing_capture import CustomerListing
from app.services import tenant_settings as ts
from tests.web_discovery_support import COUNTRY, ENDINGS

ALPHA_NAME = "Alpha Gadgets (Pty) Ltd"
BETA_NAME = "Beta Traders Ltd"
ALPHA_HOST = "alphagadgets.zz"


@dataclass
class World:
    tenant: str
    tag: str
    alpha_id: int  # a reporting customer with a contact, a line-up product and an unlinked listing
    beta_id: int  # a customer that is not reporting
    product_id: int
    listing_id: int


def seed_settings(session: Session, tenant: str, **over) -> None:
    values = {
        ts.KEY_TENANT_COUNTRY: dict(COUNTRY),
        ts.KEY_TENANT_DOMAIN_ENDINGS: list(ENDINGS),
        ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["ddg_html", "ddg_lite"],
    }
    values.update(over)
    for key, value in values.items():
        if value is not None:
            ts.set_setting(session, tenant, key, value, actor="test")


def seed_world(session: Session, tenant: str, tag: str, *, settings: bool = True) -> World:
    alpha = DimCustomer(
        code=f"WD-A-{tag}", name=ALPHA_NAME, customer_status="active", is_key_account=False, tenant_id=tenant
    )
    beta = DimCustomer(
        code=f"WD-B-{tag}", name=BETA_NAME, customer_status="active", is_key_account=False, tenant_id=tenant
    )
    session.add_all([alpha, beta])
    session.flush()
    session.add(CustomerReportConfig(customer_id=alpha.id, reports_expected=True, feed_profile_json={}))
    session.add(
        CustomerContact(
            customer_id=alpha.id, contact_name="Test Buyer", email="buyer@alphagadgets.example.test", is_active=True
        )
    )
    product = DimProduct(
        tenant_id=tenant,
        sku=f"WD-SKU-{tag}",
        part_number=f"WD-PN-{tag}",
        name="Widget One",
        sales_model_name="Widget One",
        ean="4006381333931",
    )
    session.add(product)
    session.flush()
    session.add(
        FactLineupPlanItem(
            customer_id=alpha.id, product_id=product.id, period_start=date(2026, 1, 5), planned_volume_units=1
        )
    )
    listing = CustomerListing(
        customer_id=alpha.id, product_id=None, url=f"https://{ALPHA_HOST}/p/1", marketplace=f"wd{tag}"[:32]
    )
    session.add(listing)
    session.flush()
    if settings:
        seed_settings(session, tenant)
    return World(
        tenant=tenant,
        tag=tag,
        alpha_id=int(alpha.id),
        beta_id=int(beta.id),
        product_id=int(product.id),
        listing_id=int(listing.id),
    )


_DELETE_BY_TENANT = (
    "DELETE FROM customer_web_site WHERE tenant_id = :t",
    "DELETE FROM listing_link_queue WHERE tenant_id = :t",
    "DELETE FROM listing_link WHERE tenant_id = :t",
    "DELETE FROM listing_site_seller WHERE tenant_id = :t",
    "DELETE FROM cst_listing_seed WHERE customer_id IN (SELECT id FROM dim_customer WHERE tenant_id = :t)",
    "DELETE FROM customer_listing WHERE customer_id IN (SELECT id FROM dim_customer WHERE tenant_id = :t)",
    "DELETE FROM fact_lineup_plan_item WHERE customer_id IN (SELECT id FROM dim_customer WHERE tenant_id = :t)",
    "DELETE FROM customer_contact WHERE customer_id IN (SELECT id FROM dim_customer WHERE tenant_id = :t)",
    "DELETE FROM customer_report_config WHERE customer_id IN (SELECT id FROM dim_customer WHERE tenant_id = :t)",
    "DELETE FROM listing_site WHERE tenant_id = :t",
    "DELETE FROM tenant_setting WHERE tenant_id = :t",
    "DELETE FROM dim_product WHERE tenant_id = :t",
    "DELETE FROM dim_customer WHERE tenant_id = :t",
)


def delete_tenant_rows(tenant: str) -> None:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as session:
        for statement in _DELETE_BY_TENANT:
            session.execute(text(statement), {"t": tenant})
        session.commit()


def _require_cip_test(session: Session) -> None:
    db = session.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        pytest.skip(f"web discovery DB test runs on cip_test only (current_database()={db})")


@pytest.fixture()
def outer_tx_session():
    """A session inside a transaction that is always rolled back."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    engine = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        conn = engine.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        engine.dispose()
        pytest.skip(f"web discovery DB test runs on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
        engine.dispose()


@pytest.fixture()
def world(outer_tx_session: Session) -> World:
    tag = uuid.uuid4().hex[:8]
    return seed_world(outer_tx_session, f"wd-{tag}", tag)


@pytest.fixture()
def committed_world():
    """Real rows under a unique tenant, committed, and removed afterwards."""
    from app.db.session_sync import SessionLocal

    tag = uuid.uuid4().hex[:8]
    tenant = f"wd-{tag}"
    with SessionLocal() as session:
        _require_cip_test(session)
        built = seed_world(session, tenant, tag)
        session.commit()
    try:
        yield built
    finally:
        delete_tenant_rows(tenant)
