"""Discovery V2 linking: exact decisions and rollback-only cip_test integration."""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_web_site import CustomerWebSite
from app.models.dimensions import DimCustomer, DimProduct
from app.models.iam import Tenant
from app.models.listing_capture import CustomerListing
from app.models.listing_link import (
    LINK_CONFIRMED,
    LINK_REJECTED,
    QUEUE_CONFIRMED,
    QUEUE_NOT_ON_SITE,
    QUEUE_OPEN,
    ListingLink,
    ListingLinkQueue,
)
from app.models.steward_audit import StewardAuditEvent
from app.services.listing_capture.coverage import customer_coverage
from app.services.listing_capture.links import (
    decide_queue,
    queue_listing_case,
    undo_auto_link,
)
from app.services.listing_capture.sites import create_site, site_config_from_row
from app.services.listing_capture.web_discovery import apply as web_apply
from app.services.listing_capture.web_discovery import preview
from app.services.listing_capture.web_discovery.linking import (
    AUTO_LINK,
    NONE,
    QUEUE,
    CatalogueIndex,
    decide,
    link_unlinked_listings,
)
from app.services.listing_capture.web_discovery.polite import Fetched
from app.services.listing_capture.web_discovery.settings import load_discovery_settings
from tests.rolled_back_async_session import rolled_back_async_session

WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE)\b", re.I)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _product(pid: int, **values):
    return SimpleNamespace(
        id=pid,
        tenant_id=values.pop("tenant_id", "unit"),
        name=f"Item {pid}",
        ean=values.pop("ean", None),
        upc=values.pop("upc", None),
        part_number=values.pop("part_number", None),
        sales_model_name=values.pop("sales_model_name", None),
        model_name=values.pop("model_name", None),
        **values,
    )


def _index(*products):
    return CatalogueIndex.from_products(products, "unit")


def test_unique_gtin_auto_links_with_normalised_key_and_evidence():
    index = _index(_product(1, ean="4006381333931"))
    facts = {"barcodes": ["04006381333931"], "models": [], "stock_codes": []}
    result = decide(facts, index)
    assert (result.outcome, result.product_id, result.how) == (AUTO_LINK, 1, "gtin")
    assert result.evidence["facts"] == facts
    assert result.evidence["matched_keys"] == {"4006381333931": [1]}


def test_exact_normalised_part_code_auto_links_without_a_click():
    index = _index(_product(1, part_number="AX-4200"))
    result = decide({"models": ["ax 4200"]}, index)
    assert (result.outcome, result.product_id, result.how) == (AUTO_LINK, 1, "model")


def test_shared_model_queues_both_products():
    index = _index(
        _product(1, sales_model_name="AX-4200"),
        _product(2, part_number="AX 4200"),
    )
    result = decide({"models": ["AX4200"]}, index)
    assert (result.outcome, result.reason, result.candidates) == (
        QUEUE,
        "ambiguous_identity",
        [1, 2],
    )
    assert result.to_dict(index)["candidates"] == [
        {"product_id": 1, "label": "Item 1"},
        {"product_id": 2, "label": "Item 2"},
    ]


def test_conflicting_individually_unique_barcodes_are_ambiguous():
    index = _index(_product(1, ean="4006381333931"), _product(2, ean="5901234123457"))
    result = decide({"barcodes": ["4006381333931", "5901234123457"]}, index)
    assert result.outcome == QUEUE and result.candidates == [1, 2]


def test_ambiguous_gtin_does_not_fall_through_to_a_unique_model():
    index = _index(
        _product(1, ean="4006381333931", part_number="AX4200"),
        _product(2, ean="4006381333931"),
    )
    result = decide({"barcodes": ["4006381333931"], "models": ["AX4200"]}, index)
    assert result.outcome == QUEUE and result.reason == "ambiguous_identity"


def test_gtin_precedes_a_model_when_the_gtin_is_unique():
    index = _index(
        _product(1, ean="4006381333931"),
        _product(2, part_number="AX4200"),
    )
    result = decide({"barcodes": ["4006381333931"], "models": ["AX4200"]}, index)
    assert (result.outcome, result.product_id, result.how) == (AUTO_LINK, 1, "gtin")


def test_identity_mismatch_is_queued_with_the_actual_candidate():
    index = _index(_product(1, ean="4006381333931"), _product(2))
    result = decide(
        {"barcodes": ["4006381333931"]}, index, expected_product_id=2
    )
    assert (result.outcome, result.reason, result.candidates) == (
        QUEUE,
        "identity_mismatch",
        [1],
    )


@pytest.mark.parametrize(
    "facts",
    [
        {},
        {"stock_codes": ["AX4200"]},
        {"models": ["AX4201"]},
        {"models": ["AX4"]},
        {"title": "AX4200", "brand": "AX4200"},
    ],
)
def test_weak_or_near_match_evidence_never_auto_links(facts):
    result = decide(facts, _index(_product(1, part_number="AX4200")))
    assert result.outcome == QUEUE and result.reason == "no_identity_on_page"


def test_index_excludes_other_tenants():
    index = _index(
        _product(1, part_number="AX4200"),
        _product(2, part_number="AX4200", tenant_id="another"),
    )
    assert decide({"models": ["AX4200"]}, index).product_id == 1
    assert decide({}, index, expected_product_id=2).outcome == NONE


class Getter:
    def __init__(self, *, body=None, status=200, refused=None):
        self.body = (
            '<title>Invented item</title><script type="application/ld+json">'
            '{"gtin13":"4006381333931"}</script>'
            if body is None
            else body
        )
        self.status = status
        self.refused = refused
        self.calls = []

    def get(self, url, *, gate_key, spacing):
        self.calls.append((url, gate_key, spacing))
        return Fetched(
            status=self.status,
            body=self.body,
            final_url=url,
            refused=self.refused,
        )


def _seed(session: Session):
    tag = uuid.uuid4().hex[:12]
    tenant = f"link-{tag}"
    session.add(Tenant(id=tenant, name="Synthetic linking tenant"))
    customer = DimCustomer(
        tenant_id=tenant,
        code=f"LC-{tag}",
        name="Invented Retail",
        customer_status="active",
        is_key_account=False,
    )
    product = DimProduct(
        tenant_id=tenant,
        sku=f"LP-{tag}",
        name="Invented Item",
        ean="4006381333931",
        sales_model_name="AX4200",
    )
    session.add_all([customer, product])
    session.flush()
    site = create_site(
        session,
        tenant_id=tenant,
        site_key=f"shop-{tag}",
        fields={"rate_limit_seconds": 0},
        actor="test",
    )
    listing = CustomerListing(
        customer_id=customer.id,
        product_id=None,
        marketplace=site.site_key,
        external_id=f"external-{tag}",
        url="https://shop.example.test/item/1",
    )
    session.add(listing)
    session.flush()
    return SimpleNamespace(
        tenant=tenant,
        customer=customer,
        product=product,
        site=site,
        listing=listing,
        user={"tenant_id": tenant, "email": "steward@example.test"},
    )


def _plan(session, world, *, listings=None, customers=None):
    pid = str(uuid.uuid4())
    plan = preview.new_plan(world.tenant, pid, {"scope": "unlinked_listings"})
    plan["status"] = preview.STATUS_DONE
    plan["settings_fingerprint"] = load_discovery_settings(
        session, world.tenant
    ).fingerprint()
    plan["result"] = {
        "customers": customers or [],
        "listings": listings or [],
        "totals": {},
    }
    store = preview.MemoryPlanStore()
    store.save(world.tenant, pid, plan)
    return store, pid


def _apply(session, world, store, pid):
    return web_apply.apply_plan(
        session,
        store,
        tenant_id=world.tenant,
        preview_id=pid,
        user=world.user,
    )


@pytest.mark.anyio
async def test_preview_helper_is_write_free_and_feed_mapping_sends_no_request():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            session.add(
                CstListingSeed(
                    customer_id=world.customer.id,
                    marketplace=world.site.site_key,
                    external_id=world.listing.external_id,
                    product_id=world.product.id,
                    status="confirmed",
                    raw_json={"source": "synthetic"},
                )
            )
            session.flush()
            statements = []
            connection = session.connection()

            def record(_conn, _cursor, statement, _params, _ctx, _many):
                statements.append(statement)

            event.listen(connection, "before_cursor_execute", record)
            getter = Getter()
            try:
                items = link_unlinked_listings(session, world.tenant, None, getter)
            finally:
                event.remove(connection, "before_cursor_execute", record)
            assert len(items) == 1
            assert items[0]["how"] == "feed_seed"
            assert items[0]["product_id"] == world.product.id
            assert getter.calls == []
            assert not any(WRITE.match(statement) for statement in statements)
            assert world.listing.product_id is None

        await db.run_sync(exercise)


@pytest.mark.anyio
async def test_listing_apply_is_idempotent_and_undo_preserves_evidence():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            getter = Getter()
            items = link_unlinked_listings(session, world.tenant, None, getter)
            assert items[0]["outcome"] == AUTO_LINK
            assert getter.calls[0][1] == world.site.site_key
            store, pid = _plan(session, world, listings=items)
            first = _apply(session, world, store, pid)
            assert first["listings_linked"] == 1
            assert world.listing.product_id == world.product.id
            link_id = first["auto_links"][0]["link_id"]
            link = session.get(ListingLink, link_id)
            assert link.evidence["source"] == "discovery_v2"
            assert link.evidence["facts"]["barcodes"] == ["4006381333931"]
            statements = []
            connection = session.connection()

            def record(_conn, _cursor, statement, _params, _ctx, _many):
                statements.append(statement)

            event.listen(connection, "before_cursor_execute", record)
            try:
                assert _apply(session, world, store, pid) == first
            finally:
                event.remove(connection, "before_cursor_execute", record)
            assert not any(WRITE.match(statement) for statement in statements)
            undone = undo_auto_link(
                session,
                tenant_id=world.tenant,
                link_id=link_id,
                user=world.user,
            )
            assert undone["undone"] is True and link.status == LINK_REJECTED
            assert world.listing.product_id is None
            assert link.evidence["undo"]["undone_by"] == world.user["email"]
            audit_count = session.scalar(
                select(func.count(StewardAuditEvent.id)).where(
                    StewardAuditEvent.tenant_id == world.tenant,
                    StewardAuditEvent.action == "discovery_auto_link_undo",
                )
            )
            assert audit_count == 1
            assert undo_auto_link(
                session,
                tenant_id=world.tenant,
                link_id=link_id,
                user=world.user,
            ) == undone
            after = link_unlinked_listings(session, world.tenant, None, Getter())
            assert after[0]["outcome"] == NONE

        await db.run_sync(exercise)


@pytest.mark.anyio
async def test_unreadable_listing_queues_null_product_and_steward_links_it():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            items = link_unlinked_listings(
                session,
                world.tenant,
                None,
                Getter(body="<title>Unavailable</title>", status=403, refused="site_paused"),
            )
            assert items[0]["reason"] == "page_unreadable"
            store, pid = _plan(session, world, listings=items)
            result = _apply(session, world, store, pid)
            assert result["listings_queued"] == 1
            row = session.scalar(
                select(ListingLinkQueue).where(
                    ListingLinkQueue.tenant_id == world.tenant,
                    ListingLinkQueue.listing_id == world.listing.id,
                )
            )
            assert row.product_id is None and row.status == QUEUE_OPEN
            assert row.evidence["http_status"] == 403
            assert row.evidence["title"] == "Unavailable"
            coverage = customer_coverage(session, world.tenant)
            assert coverage["data_unavailable"] is False
            assert any(
                item["customer_id"] == world.customer.id for item in coverage["customers"]
            )
            decide_queue(
                session,
                row,
                action="link_product",
                product_id=world.product.id,
                url=None,
                actor=world.user["email"],
            )
            assert world.listing.product_id == world.product.id
            assert row.status == QUEUE_CONFIRMED and row.product_id is None
            link = session.scalar(
                select(ListingLink).where(ListingLink.tenant_id == world.tenant)
            )
            assert link.url == world.listing.url
            assert link.status == LINK_CONFIRMED
            assert link.evidence["steward"] is True

        await db.run_sync(exercise)


@pytest.mark.anyio
async def test_null_product_decision_rejects_foreign_product_and_allows_not_on_site():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            other = _seed(session)
            row = queue_listing_case(
                session,
                site=site_config_from_row(world.site),
                listing=world.listing,
                reason="no_identity_on_page",
                candidates=[],
                evidence={"listing_url": world.listing.url},
            )
            with pytest.raises(ValueError, match="same tenant|this tenant"):
                decide_queue(
                    session,
                    row,
                    action="link_product",
                    product_id=other.product.id,
                    url=None,
                    actor="test",
                )
            assert world.listing.product_id is None and row.status == QUEUE_OPEN
            with pytest.raises(ValueError, match="link_product or not_on_site"):
                decide_queue(
                    session, row, action="confirm", url=world.listing.url, actor="test"
                )
            decide_queue(session, row, action="not_on_site", url=None, actor="test")
            assert row.status == QUEUE_NOT_ON_SITE
            assert world.listing.product_id is None

        await db.run_sync(exercise)


@pytest.mark.anyio
async def test_apply_skips_a_changed_listing_and_a_forged_automatic_decision():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            items = link_unlinked_listings(session, world.tenant, None, Getter())
            store, pid = _plan(session, world, listings=items)
            world.listing.url = "https://shop.example.test/item/changed"
            session.flush()
            result = _apply(session, world, store, pid)
            assert result["listings_linked"] == 0
            assert result["skipped"][0]["reason"] == "changed_since_preview"

            weak = link_unlinked_listings(
                session, world.tenant, None, Getter(body="<title>Stock AX4200</title>")
            )
            weak[0].update(
                outcome=AUTO_LINK,
                product_id=world.product.id,
                how="model",
                reason=None,
            )
            store, pid = _plan(session, world, listings=weak)
            forged = _apply(session, world, store, pid)
            assert forged["listings_linked"] == 0 and len(forged["skipped"]) == 1
            assert world.listing.product_id is None

        await db.run_sync(exercise)


@pytest.mark.anyio
async def test_apply_rechecks_catalogue_uniqueness_and_feed_mapping():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            getter = Getter(body='<script>{"model":"AX4200"}</script>')
            items = link_unlinked_listings(session, world.tenant, None, getter)
            assert items[0]["how"] == "model"
            store, pid = _plan(session, world, listings=items)
            session.add(
                DimProduct(
                    tenant_id=world.tenant,
                    sku=f"duplicate-{uuid.uuid4().hex}",
                    name="Another synthetic item",
                    part_number="AX-4200",
                )
            )
            session.flush()
            result = _apply(session, world, store, pid)
            assert result["listings_linked"] == 0 and len(result["skipped"]) == 1

            seed = CstListingSeed(
                customer_id=world.customer.id,
                marketplace=world.site.site_key,
                external_id=world.listing.external_id,
                product_id=world.product.id,
                status="confirmed",
            )
            session.add(seed)
            session.flush()
            feed = link_unlinked_listings(session, world.tenant, None, Getter())
            store, pid = _plan(session, world, listings=feed)
            seed.product_id = None
            session.flush()
            result = _apply(session, world, store, pid)
            assert result["listings_linked"] == 0 and len(result["skipped"]) == 1

        await db.run_sync(exercise)


def _page_plan(session, world, *, complete):
    session.add(
        CustomerWebSite(
            tenant_id=world.tenant,
            customer_id=world.customer.id,
            domain="shop.example.test",
            site_id=world.site.id,
            status="confirmed",
            source="steward",
            evidence={},
        )
    )
    session.flush()
    facts = {"barcodes": ["4006381333931"], "models": [], "stock_codes": []}
    page = decide(
        facts,
        CatalogueIndex.load(session, world.tenant),
        expected_product_id=world.product.id,
    ).to_dict(CatalogueIndex.load(session, world.tenant))
    page.update(
        item_id="p-1",
        product_id=world.product.id,
        url="https://shop.example.test/item/discovered",
        capture={},
    )
    if complete:
        page["capture"] = {
            "price": 100,
            "availability": "in_stock",
            "seller": "Invented Retail",
            "buy_box": {
                "price": 100,
                "availability": "in_stock",
                "seller": "Invented Retail",
            },
        }
    block = {
        "customer_id": world.customer.id,
        "candidates": [],
        "sites": [
            {
                "domain": "shop.example.test",
                "site_key": world.site.site_key,
                "state": "existing",
                "pages": [page],
                "search_pattern": {"value": None, "how": "none"},
            }
        ],
    }
    return _plan(session, world, customers=[block])


@pytest.mark.anyio
@pytest.mark.parametrize("complete", [False, True])
async def test_page_exact_identity_links_even_without_complete_capture_and_undoes(complete):
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            store, pid = _page_plan(session, world, complete=complete)
            result = _apply(session, world, store, pid)
            assert result["pages_linked"] == 1
            assert result["pages_queued"] == 0
            assert result["proposals_created"] == int(complete)
            link_id = result["auto_links"][0]["link_id"]
            assert result["auto_links"][0]["undo_url"].endswith(f"/{link_id}/undo")
            assert world.listing.product_id is None
            undo_auto_link(
                session,
                tenant_id=world.tenant,
                link_id=link_id,
                user=world.user,
            )
            assert session.get(ListingLink, link_id).status == LINK_REJECTED
            assert session.scalar(
                select(func.count(CstListingSeed.id)).where(
                    CstListingSeed.customer_id == world.customer.id
                )
            ) == 0

        await db.run_sync(exercise)


@pytest.mark.anyio
async def test_undo_refuses_a_later_listing_edit_without_partial_reversal():
    async with rolled_back_async_session() as db:
        def exercise(session):
            world = _seed(session)
            items = link_unlinked_listings(session, world.tenant, None, Getter())
            store, pid = _plan(session, world, listings=items)
            result = _apply(session, world, store, pid)
            link_id = result["auto_links"][0]["link_id"]
            world.listing.url = "https://shop.example.test/item/steward-edited"
            session.flush()
            before = deepcopy(session.get(ListingLink, link_id).evidence)
            with pytest.raises(ValueError, match="listing changed"):
                undo_auto_link(
                    session,
                    tenant_id=world.tenant,
                    link_id=link_id,
                    user=world.user,
                )
            assert world.listing.product_id == world.product.id
            assert session.get(ListingLink, link_id).status == LINK_CONFIRMED
            assert session.get(ListingLink, link_id).evidence == before
            with pytest.raises(LookupError):
                undo_auto_link(
                    session,
                    tenant_id="another-tenant",
                    link_id=link_id,
                    user=world.user,
                )

        await db.run_sync(exercise)
