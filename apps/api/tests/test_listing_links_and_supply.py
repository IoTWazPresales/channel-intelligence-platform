"""Learned links, buy-box offers, and distributor supply. Fictional tenants. cip_test rolls back."""

from __future__ import annotations

import json
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactSalesSellout
from app.models.listing_capture import CustomerListing
from app.models.listing_link import LINK_CONFIRMED, LINK_REJECTED, QUEUE_NOT_ON_SITE, QUEUE_OPEN
from app.models.listing_offer import ListingOffer
from app.models.listing_site import ListingSite, ListingSiteSeller
from app.services.listing_capture.identity import barcodes_match, corroboration, models_match
from app.services.listing_capture.links import decide_queue, learn_link, list_open_queue
from app.services.listing_capture.registry import record_observation
from app.services.listing_capture.supply import NOT_LINKED, sellout_supply
from tests.listing_site_fixtures import REST_API, REST_HOST, rest_site


def test_match_is_exact_and_a_stock_code_is_not_a_model_or_barcode() -> None:
    assert barcodes_match(["0004711387767535"], ["4711387767535"])
    assert not barcodes_match(["4711387767536"], ["4711387767535"])
    assert models_match(["GLIDE14"], ["glide-14"])
    assert not models_match(["GLIDE"], ["GLIDE14"])
    assert not models_match(["GLIDE14X"], ["GLIDE14"])
    product = SimpleNamespace(ean="4711387767535", upc=None, part_number="GLIDE14", model_name=None, sales_model_name=None)
    assert corroboration({"barcodes": [], "models": [], "stock_codes": ["222547542"]}, product) is None
    assert corroboration({"barcodes": ["4711387767535"], "models": [], "stock_codes": ["999"]}, product) == "barcode"


def _details(*, price: float = 100, selected_price: float = 80, sku: int = 111, other: bool = True) -> dict:
    data = {
        "desktop_href": f"{REST_HOST}/northwind-glide/ID98174082",
        "buybox": {
            "plid": 98174082,
            "items": [
                {"is_selected": False, "sku": sku, "price": price, "is_add_to_cart_available": True, "stock_availability": {"status": "In stock"}},
                {"is_selected": True, "sku": 999, "price": selected_price, "is_add_to_cart_available": True, "stock_availability": {"status": "In stock"}},
            ],
        },
        "seller_detail": {"display_name": "Other Shop", "seller_id": "S-2"},
        "flixmedia": {"ean": "4711387767535"},
    }
    if other:
        data["other_offers"] = {
            "conditions": [
                {"condition": "new", "items": [{"id": "o1", "price": 70, "seller": {"display_name": "Third Shop", "seller_id": "S-3"}, "stock_availability": {"is_in_stock": True, "status": "In stock"}}]}
            ]
        }
    return data


def test_shoppers_price_is_the_buy_box_and_every_offer_is_kept() -> None:
    from app.services.listing_capture.adapters.rest_buybox import parse

    parsed = parse(json.dumps(_details()), site=rest_site(), preferred_sku="111", parser_version="t")
    assert parsed.price == 80.0  # selected buy box, not the stock-code item at 100
    assert parsed.flags["sku_matched"] is False
    assert len(parsed.offers or []) == 3
    buy = [o for o in parsed.offers or [] if o["is_buy_box"]]
    assert len(buy) == 1 and buy[0]["price"] == 80 and buy[0]["seller_name"] == "Other Shop"
    assert any(o["seller_name"] == "Third Shop" and o["price"] == 70 for o in parsed.offers or [])


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"runs on cip_test only (current_database()={db})")
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


def _world(session: Session):
    tag = uuid.uuid4().hex[:8]
    tenant = f"t-link-{tag}"
    customer = DimCustomer(code=f"C-{tag}", name=f"Customer {tag}", customer_status="active", is_key_account=False, tenant_id=tenant)
    product = DimProduct(tenant_id=tenant, sku=f"SKU-{tag}", name=f"Glide {tag}", ean="4711387767535", model_name="GLIDE14", is_active=True)
    distributor = DimDistributor(tenant_id=tenant, code=f"D-{tag}", name=f"Dist {tag}", distributor_status="active")
    session.add_all([customer, product, distributor])
    session.flush()
    site = ListingSite(
        tenant_id=tenant,
        site_key="market-b",
        display_name="Market B",
        adapter_key="rest_buybox_json",
        product_url_pattern=f"{REST_HOST}/x/ID{{page_id}}",
        page_id_pattern=r"ID(\d{5,12})",
        details_url_pattern=f"{REST_API}/rest/details/ID{{page_id}}?platform=desktop",
        search_url_pattern=f"{REST_API}/rest/search?q={{query}}",
        first_party_seller="Market B Retail",
    )
    session.add(site)
    session.flush()
    session.add(
        ListingSiteSeller(
            tenant_id=tenant,
            site_id=int(site.id),
            customer_id=int(customer.id),
            seller_names=["Market B Retail"],
            seller_ids=[],
        )
    )
    listing = CustomerListing(
        customer_id=int(customer.id),
        product_id=int(product.id),
        url=f"{REST_HOST}/ID222547542",
        marketplace="market-b",
        status="active",
        source="manual",
        external_id="222547542",
    )
    session.add(listing)
    session.flush()
    return SimpleNamespace(tag=tag, tenant=tenant, customer=customer, product=product, distributor=distributor, site=site, listing=listing)


def test_ambiguous_search_is_queued_and_a_steward_confirm_is_remembered(db_session: Session) -> None:
    world = _world(db_session)
    search = {
        "sections": {
            "products": {
                "results": [
                    {"product_views": {"core": {"id": 98174082, "title": "Glide one", "slug": "glide-one"}}},
                    {"product_views": {"core": {"id": 98174083, "title": "Glide two", "slug": "glide-two"}}},
                ]
            }
        }
    }

    def http_get(url: str, headers=None):
        if "details" in url:
            return 404, "{}"
        return 200, json.dumps(search)

    result = learn_link(db_session, world.listing, _site_config(world), http_get=http_get)
    assert result["status"] == "queued" and result["reason"] == "ambiguous"
    assert len(result["candidates"]) == 2
    open_rows = list_open_queue(db_session)
    assert any(r.product_id == world.product.id and r.status == QUEUE_OPEN for r in open_rows)
    row = next(r for r in open_rows if r.product_id == world.product.id)
    decide_queue(db_session, row, action="confirm", url=result["candidates"][0]["url"], actor="steward@example.test")
    assert world.listing.url == result["candidates"][0]["url"]
    again = learn_link(db_session, world.listing, _site_config(world), http_get=http_get)
    assert again["status"] == "confirmed" and again["source"] == "remembered"
    decide_row = db_session.scalars(select(type(row)).where(type(row).id == row.id)).one()
    assert decide_row.status == "confirmed"


def test_reject_is_remembered_and_not_on_site_stops_learning(db_session: Session) -> None:
    world = _world(db_session)
    site = _site_config(world)

    def http_get(url: str, headers=None):
        if "details" in url:
            return 404, "{}"
        return 200, json.dumps({"sections": {"products": {"results": []}}})

    learn_link(db_session, world.listing, site, http_get=http_get)
    row = next(r for r in list_open_queue(db_session) if r.product_id == world.product.id)
    decide_queue(db_session, row, action="not_on_site", url=None, actor="steward@example.test")
    assert row.status == QUEUE_NOT_ON_SITE
    again = learn_link(db_session, world.listing, site, http_get=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no fetch")))
    assert again["status"] == "not_on_site"

    world2 = _world(db_session)
    site2 = _site_config(world2)
    learn_link(db_session, world2.listing, site2, http_get=http_get)
    queued = next(r for r in list_open_queue(db_session) if r.product_id == world2.product.id)
    url = f"{REST_HOST}/x/ID98174082"
    decide_queue(db_session, queued, action="reject", url=url, actor="steward@example.test")
    from app.models.listing_link import ListingLink

    remembered = db_session.scalars(select(ListingLink).where(ListingLink.product_id == world2.product.id)).one()
    assert remembered.status == LINK_REJECTED and remembered.url == url
    assert LINK_CONFIRMED != remembered.status


def test_record_observation_stores_every_offer_and_labels_competition(db_session: Session) -> None:
    world = _world(db_session)
    body = json.dumps(_details())

    def http_get(url: str, headers=None):
        if url.endswith("ID222547542?platform=desktop") or "ID222547542" in url and "details" in url:
            return 404, "{}"
        if "search" in url:
            return 200, json.dumps({"sections": {"products": {"results": [{"product_views": {"core": {"id": 98174082}}}]}}})
        if "ID98174082" in url:
            return 200, body
        raise AssertionError(url)

    obs = record_observation(db_session, world.listing, http_get=http_get)
    assert float(obs.extracted_price) == 80.0
    assert obs.buy_box_seller == "Other Shop"
    assert obs.buy_box_own is False
    assert obs.offer_count == 3
    offers = list(db_session.scalars(select(ListingOffer).where(ListingOffer.observation_id == obs.id)).all())
    assert len(offers) == 3
    assert sum(1 for o in offers if o.is_buy_box) == 1
    assert world.listing.url.startswith(REST_HOST)


def test_supply_is_the_resolved_sellout_or_not_linked(db_session: Session) -> None:
    world = _world(db_session)
    empty = sellout_supply(db_session, customer_id=world.customer.id, product_id=world.product.id, tenant_id=world.tenant)
    assert empty["status"] == NOT_LINKED and empty["rows"] == []
    db_session.add(
        FactSalesSellout(
            source_key=f"src-{world.tag}",
            tenant_id=world.tenant,
            product_id=world.product.id,
            customer_id=world.customer.id,
            distributor_id=world.distributor.id,
            period_start=date(2026, 10, 1),
            transaction_date=date(2026, 10, 4),
            invoice_no="INV-1",
            units=4,
            revenue=400,
            unit_sellout_price_ex_tax_amount=100,
            currency_code="ZAR",
        )
    )
    db_session.flush()
    linked = sellout_supply(db_session, customer_id=world.customer.id, product_id=world.product.id, tenant_id=world.tenant)
    assert linked["status"] == "linked"
    assert linked["rows"][0]["distributor"] == world.distributor.name
    assert linked["rows"][0]["units"] == 4
    assert linked["rows"][0]["price"] == 100
    assert linked["rows"][0]["period"] == "2026-10-01"
    # A different product is not linked. No name is consulted.
    other = sellout_supply(db_session, customer_id=world.customer.id, product_id=world.product.id + 999999, tenant_id=world.tenant)
    assert other["status"] == NOT_LINKED
    assert sellout_supply(db_session, customer_id=world.customer.id, product_id=None, tenant_id=world.tenant)["status"] == NOT_LINKED


def _site_config(world):
    from app.services.listing_capture.sites import site_config_from_row

    return site_config_from_row(world.site)
