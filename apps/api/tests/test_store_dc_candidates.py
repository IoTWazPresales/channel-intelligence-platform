"""Unit 2: ask once, remember confirm and reject, never create a location."""

import pytest
from sqlalchemy import func, select

from app.models.dimensions import CustomerLocation
from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import decide_candidate, refresh_candidates, save_tenant_config

from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


def _open(world: World) -> list[SiteCandidate]:
    return list(
        world.db.execute(select(SiteCandidate).where(SiteCandidate.tenant_id == world.tenant).order_by(SiteCandidate.id)).scalars()
    )


def test_direct_shipment_asks_once_and_creates_no_location(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    label = world.code("SDC-SHIPTO")
    world.shipment(customer=customer, distributor=distributor, ship_to=label)
    world.db.flush()
    before_locations = world.counts()[2]
    first = refresh_candidates(world.db, world.tenant)
    assert first["inserted"] == 1
    assert first["locations_created"] == 0
    assert world.counts()[2] == before_locations
    row = _open(world)[0]
    assert row.evidence_kind == "direct_shipment"
    assert row.status == "open"
    assert row.location_id is None
    second = refresh_candidates(world.db, world.tenant)
    assert second["inserted"] == 0
    assert len(_open(world)) == 1
    decided = decide_candidate(world.db, world.tenant, row.id, "confirm", "steward-test")
    assert decided["status"] == "confirmed"
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == before_locations
    again = refresh_candidates(world.db, world.tenant)
    assert again["inserted"] == 0
    world.db.refresh(row)
    assert row.status == "confirmed"


def test_reject_is_remembered(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    label = world.code("SDC-SHIPTO")
    world.shipment(customer=customer, distributor=distributor, ship_to=label)
    world.db.flush()
    refresh_candidates(world.db, world.tenant)
    row = _open(world)[0]
    decide_candidate(world.db, world.tenant, row.id, "reject", "steward-test")
    refresh_candidates(world.db, world.tenant)
    world.db.refresh(row)
    assert row.status == "rejected"


def test_pattern_is_fullmatch_and_stock_behaviour_stays_a_candidate(world: World):
    customer = world.customer("SDC-C")
    product = world.product()
    save_tenant_config(world.db, world.tenant, dc_name_patterns=[r"^SDC-HUB-.+$"])
    hub = world.code("SDC-HUB-1")
    almost = f"note {hub}"
    quiet = world.code("SDC-QUIET")
    world.weeks(customer, product, [0, 0, 0, 0], soh=8, site=quiet)
    world.weeks(customer, product, [3, 3, 3, 3], soh=1, site=hub)
    world.weeks(customer, product, [3, 3, 3, 3], soh=1, site=almost)
    world.db.flush()
    before = world.counts()[2]
    refresh_candidates(world.db, world.tenant)
    rows = {row.site_label: row for row in _open(world)}
    assert rows[hub].evidence_kind == "pattern"
    assert rows[quiet].evidence_kind == "stock_behaviour"
    assert almost not in rows
    assert world.counts()[2] == before


def test_distributor_warehouse_cannot_be_confirmed(world: World):
    before = world.counts()[2]
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    warehouse = world.distributor_location(distributor, "SDC-WH")
    world.shipment(customer=customer, distributor=distributor, ship_to=warehouse.location_name)
    world.db.flush()
    refresh_candidates(world.db, world.tenant)
    row = _open(world)[0]
    assert row.blocked_as_distributor_site is True
    with pytest.raises(ValueError):
        decide_candidate(world.db, world.tenant, row.id, "confirm", "steward-test")
    world.db.refresh(row)
    assert row.status == "open"
    assert world.counts()[2] == before
