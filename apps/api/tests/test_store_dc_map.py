"""Unit 8: one dot per store per customer. A pin is the only location this module creates."""

import pytest

from sqlalchemy import func, select

from app.models.dimensions import CustomerLocation
from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import decide_candidate, refresh_candidates
from app.services.store_dc.map import build_store_map, drop_pin

from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


def test_a_store_without_coordinates_is_not_pinned_and_a_pin_is_remembered(world: World):
    first = world.customer("SDC-C1")
    second = world.customer("SDC-C2")
    product = world.product()
    shared = world.code("SDC-SITE-A")
    loose = world.code("SDC-SITE-B")
    world.weeks(first, product, [4, 6], soh=4, site=shared)
    world.weeks(second, product, [1, 1], soh=9, site=shared)
    world.weeks(first, product, [2], soh=2, site=loose)
    world.db.flush()
    before = build_store_map(world.db, world.tenant)
    assert len(before["stores"]) == 3
    assert all(store["pinned"] is False and store["latitude"] is None for store in before["stores"])
    assert {store["customer_id"] for store in before["stores"] if store["site_label"] == shared} == {first.id, second.id}
    locations_before = world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
    pinned = drop_pin(
        world.db,
        tenant_id=world.tenant,
        customer_id=first.id,
        site_label=shared,
        latitude=1.5,
        longitude=2.5,
        actor="steward-test",
    )
    assert pinned["pinned"] is True
    assert pinned["latitude"] == 1.5
    assert pinned["longitude"] == 2.5
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == locations_before + 1
    other = drop_pin(
        world.db,
        tenant_id=world.tenant,
        customer_id=second.id,
        site_label=shared,
        latitude=1.5,
        longitude=2.5,
        actor="steward-test",
    )
    assert other["customer_id"] != pinned["customer_id"]
    again = build_store_map(world.db, world.tenant)
    dots = [store for store in again["stores"] if store["pinned"]]
    assert len(dots) == 2
    assert dots[0]["latitude"] == dots[1]["latitude"] == 1.5
    unpinned = [store for store in again["stores"] if not store["pinned"]]
    assert len(unpinned) == 1
    assert unpinned[0]["site_label"] == loose
    ratio = pinned["sell_through"]
    assert ratio == round(6 / (6 + 4), 4)
    with pytest.raises(LookupError):
        drop_pin(
            world.db,
            tenant_id=world.tenant,
            customer_id=first.id,
            site_label=world.code("SDC-MISSING"),
            latitude=1.5,
            longitude=2.5,
            actor="steward-test",
        )


def test_refresh_does_not_create_a_location_and_a_confirmed_dc_is_not_a_store_dot(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    hub = world.code("SDC-HUB-1")
    store = world.code("SDC-SITE-A")
    locations_before = world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
    world.weeks(customer, product, [0, 0], soh=9, site=hub)
    world.weeks(customer, product, [2, 2], soh=2, site=store)
    world.shipment(customer=customer, distributor=distributor, ship_to=hub)
    world.db.flush()
    created = refresh_candidates(world.db, world.tenant)
    assert created["locations_created"] == 0
    candidate = world.db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub)
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")
    payload = build_store_map(world.db, world.tenant, [customer.id])
    assert [row["site_label"] for row in payload["stores"]] == [store]
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == locations_before
