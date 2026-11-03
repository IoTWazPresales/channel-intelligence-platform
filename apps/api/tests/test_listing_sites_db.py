"""Listing sites and sellers are tenant data: service + SQL on cip_test (rolled back). Fictional tenants.

Skips on any database other than cip_test.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.tenant_scope import install_tenant_select_scope, request_tenant_id
from app.models.dimensions import DimCustomer
from app.models.listing_capture import CustomerListing
from app.services.listing_capture import sites as site_service
from app.services.listing_capture.registry import create_listing, poll_active_listings, record_observation


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"listing sites DB test runs on cip_test only (current_database()={db})")
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


def _tenant_customer(session: Session, tenant: str, label: str) -> DimCustomer:
    tag = uuid.uuid4().hex[:6]
    row = DimCustomer(code=f"{label}-{tag}", name=f"{label} {tag}", customer_status="active", is_key_account=False, tenant_id=tenant)
    session.add(row)
    session.flush()
    return row


@pytest.fixture()
def world(db_session: Session):
    tag = uuid.uuid4().hex[:6]
    t1, t2 = f"t-one-{tag}", f"t-two-{tag}"
    c1 = _tenant_customer(db_session, t1, "Alpha")
    c2 = _tenant_customer(db_session, t2, "Beta")
    return SimpleNamespace(session=db_session, t1=t1, t2=t2, c1=c1, c2=c2)


def test_create_validate_update_and_seller_round_trip(world) -> None:
    s = world.session
    row = site_service.create_site(s, tenant_id=world.t1, site_key=" Shop-A ", fields={"display_name": "Shop A"}, actor="steward@x")
    assert row.site_key == "shop-a" and row.adapter_key is None
    payload = site_service.site_to_dict(row)
    assert payload["configured"] is False and payload["missing_fields"] == ["adapter_key"]

    with pytest.raises(ValueError, match="already exists"):
        site_service.create_site(s, tenant_id=world.t1, site_key="shop-a", fields={}, actor=None)
    # Same key in another tenant is a different site.
    other = site_service.create_site(s, tenant_id=world.t2, site_key="shop-a", fields={}, actor=None)
    assert other.id != row.id

    for bad, match in (
        ({"adapter_key": "nope"}, "unknown adapter_key"),
        ({"product_url_pattern": "shop-a.example.test/{page_id}"}, "http"),
        ({"product_url_pattern": "https://shop-a.example.test/p"}, "{page_id}"),
        ({"search_url_pattern": "https://shop-a.example.test/s"}, "{query}"),
        ({"page_id_pattern": "ID(\\d+"}, "not a valid pattern"),
        ({"page_id_pattern": "ID\\d+"}, "exactly one capture group"),
        ({"rate_limit_seconds": -1}, "between"),
        ({"display_name": "  "}, "display_name required"),
    ):
        with pytest.raises(ValueError, match=match):
            site_service.update_site(s, row, fields=bad, actor=None)

    site_service.update_site(
        s,
        row,
        fields={
            "adapter_key": "rest_buybox_json",
            "product_url_pattern": "https://shop-a.example.test/x/ID{page_id}",
            "details_url_pattern": "https://api.shop-a.example.test/d/ID{page_id}",
            "page_id_pattern": "ID(\\d+)",
            "rate_limit_seconds": "1.5",
        },
        actor="steward@x",
    )
    payload = site_service.site_to_dict(row)
    assert payload["configured"] is True and payload["missing_fields"] == []
    assert payload["rate_limit_seconds"] == 1.5 and payload["updated_by"] == "steward@x"

    with pytest.raises(ValueError, match="different tenants"):
        site_service.set_site_seller(s, row, customer_id=world.c2.id, seller_names=["B"], seller_ids=[], actor=None)
    with pytest.raises(ValueError, match="at least one"):
        site_service.set_site_seller(s, row, customer_id=world.c1.id, seller_names=[" "], seller_ids=[], actor=None)
    site_service.set_site_seller(
        s, row, customer_id=world.c1.id, seller_names=["Alpha Store", "alpha  store", "Alpha Outlet"], seller_ids=["S1"], actor="a"
    )
    site_service.set_site_seller(s, row, customer_id=world.c1.id, seller_names=["Alpha Store"], seller_ids=[], actor="b")
    s.expire_all()
    fresh = site_service.get_site(s, row.id)
    assert [(x.customer_id, x.seller_names, x.seller_ids) for x in fresh.sellers] == [(world.c1.id, ["Alpha Store"], [])]
    config = site_service.site_config_from_row(fresh)
    assert config.is_own_seller(world.c1.id, name="ALPHA  store") is True
    assert config.is_own_seller(world.c1.id, name="Alpha Store Two") is False
    assert config.is_own_seller(world.c2.id, name="Alpha Store") is None

    assert site_service.delete_site_seller(s, fresh, customer_id=world.c1.id) is True
    assert site_service.delete_site_seller(s, fresh, customer_id=world.c1.id) is False
    assert s.execute(text("select count(*) from listing_site_seller where site_id = :i"), {"i": row.id}).scalar_one() == 0


def test_lookup_is_by_the_customers_tenant(world) -> None:
    s = world.session
    site_service.create_site(s, tenant_id=world.t1, site_key="shop-a", fields={"adapter_key": "html_page"}, actor=None)
    assert site_service.site_for_customer(s, world.c1.id, "SHOP-A").site_key == "shop-a"
    assert site_service.site_for_customer(s, world.c2.id, "shop-a") is None  # tenant two has no such site
    assert site_service.site_for_customer(s, 2_000_000_000, "shop-a") is None

    listing = create_listing(s, customer_id=world.c1.id, url="https://shop-a.example.test/p/1", marketplace="shop-a")
    assert listing.id is not None
    with pytest.raises(ValueError, match="unknown site"):
        create_listing(s, customer_id=world.c2.id, url="https://shop-a.example.test/p/2", marketplace="shop-a")

    resolver = site_service.SiteResolver.load(s, [listing, SimpleNamespace(customer_id=world.c2.id, marketplace="shop-a")])
    assert resolver.site_for(listing).tenant_id == world.t1
    assert resolver.site_for(SimpleNamespace(customer_id=world.c2.id, marketplace="shop-a")) is None


def test_orm_reads_are_scoped_to_the_request_tenant(world) -> None:
    s = world.session
    install_tenant_select_scope()
    site_service.create_site(s, tenant_id=world.t1, site_key="shop-a", fields={}, actor=None)
    site_service.create_site(s, tenant_id=world.t2, site_key="shop-b", fields={}, actor=None)
    token = request_tenant_id.set(world.t2)
    try:
        assert [r.site_key for r in site_service.list_sites(s)] == ["shop-b"]
    finally:
        request_tenant_id.reset(token)


def test_unconfigured_site_is_skipped_by_record_and_poll(world) -> None:
    s = world.session
    site_service.create_site(s, tenant_id=world.t1, site_key="shop-c", fields={}, actor=None)
    listing = CustomerListing(customer_id=world.c1.id, url="https://shop-c.example.test/p", marketplace="shop-c", status="active", source="manual")
    s.add(listing)
    s.flush()

    def no_http(url, headers=None):
        raise AssertionError(f"unexpected GET {url}")

    obs = record_observation(s, listing, http_get=no_http)
    assert obs.parse_status == "skipped" and obs.parse_flags["reason"] == "site_not_configured"
    out = poll_active_listings(s, marketplaces=["shop-c"], http_get=no_http, pause_store=None, log_result=False)
    assert out["polled"] == 0
    assert out["skipped_not_configured"].get("shop-c", 0) >= 1
    assert listing.id not in out["considered_ids"]
